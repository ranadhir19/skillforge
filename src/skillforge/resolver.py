"""Two-stage skill retrieval and triggering (design Part 3.2).

Stage 1 is deterministic candidate generation over the whole library:
a BM25-lite token-overlap score and a hashed-embedding cosine over
each skill's metadata (name, description, trigger examples). It
shortlists ~12 candidates. Stage 2 reranks the shortlist; the
production design calls for a model rerank with the negative examples
in context. Here stage 2 ships two implementations of one interface:

- ``DeterministicReranker`` — the offline default. Scores example
  proximity, description proximity and stage-1 evidence, and applies
  a counter-example penalty scaled by *counter dominance*: how much
  better the nearest near-miss explains the task than the best
  positive example does. A near-miss that merely shares vocabulary
  with a strong positive match does not veto it; a near-miss that
  explains the task as well as or better than every example does.
  Every decision is logged with its reason; nothing is a coin flip.
- ``ModelReranker`` — used when a completion callable is supplied
  (e.g. a real provider behind the seam); parses the model's JSON
  selection. Key-gated by construction: no callable, no reranker.

On top of scores, hard gates apply in order: lifecycle (only
``active`` skills govern; ``shadow`` skills are scored and logged but
never govern), capability requirements vs the bound provider's
capability set (excluded *with the reason surfaced*), declared
conflicts (resolved deterministically by specificity = final score),
user pins (always win), and a cap K on co-active skills.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "for", "in",
             "on", "with", "me", "my", "our", "your", "please", "this",
             "that", "it", "is", "are", "do", "does", "what", "how"}

FIRE_THRESHOLD = 0.30
MAX_ACTIVE = 4
SHORTLIST_K = 12
EMB_DIM = 256


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def _embed(text: str) -> list[float]:
    vec = [0.0] * EMB_DIM
    for tok in set(tokens(text)):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % EMB_DIM] += 1.0 if (h >> 8) % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class ScoredSkill:
    name: str
    score: float
    detail: dict = field(default_factory=dict)


@dataclass
class Resolution:
    active: list                    # [ScoredSkill], governing, best first
    primary: str | None             # the top governing skill (or pin)
    shadow_hits: list               # [ScoredSkill] scored but shadow-state
    excluded: list                  # [(name, reason)] — always with a reason
    log: list                       # human-readable decision lines

    def names(self) -> list[str]:
        return [s.name for s in self.active]


class DeterministicReranker:
    """Stage 2, offline: example/counter-example aware scoring."""

    name = "deterministic"

    def score(self, pkg, task_text: str, stage1: float) -> ScoredSkill:
        q = set(tokens(task_text))
        ex_best = 0.0
        for ex in pkg.manifest.trigger_examples:
            ex_best = max(ex_best, _overlap(q, set(tokens(ex))))
        counter_best = 0.0
        for cx in pkg.manifest.trigger_counter_examples:
            counter_best = max(counter_best, _overlap(q, set(tokens(cx))))
        desc = _overlap(q, set(tokens(pkg.description)) |
                        set(tokens(pkg.name.replace("-", " "))))
        # Counter penalty, scaled by counter dominance: the fraction
        # of the counter match not already explained by the best
        # positive example. penalty = 0.9 * counter^2 / max(ex, counter).
        if counter_best > 0:
            dominance = counter_best / max(ex_best, counter_best)
            penalty = 0.90 * counter_best * dominance
        else:
            penalty = 0.0
        score = (0.60 * ex_best + 0.25 * desc + 0.15 * stage1
                 - penalty)
        return ScoredSkill(pkg.name, round(score, 4),
                           {"example": round(ex_best, 3),
                            "counter": round(counter_best, 3),
                            "counter_penalty": round(penalty, 3),
                            "description": round(desc, 3),
                            "stage1": round(stage1, 3)})


class ModelReranker:  # pragma: no cover - exercised only with a live model
    """Stage 2 with a real model behind the seam. ``complete`` is a
    callable prompt -> text supplied by the caller (key-gated)."""

    name = "model"

    def __init__(self, complete):
        self._complete = complete

    def score(self, pkg, task_text: str, stage1: float) -> ScoredSkill:
        prompt = (
            "Decide whether the skill should fire for the task. Reply "
            "with JSON {\"score\": 0..1}.\n"
            f"Skill: {pkg.name}\nDescription: {pkg.description}\n"
            f"Should fire for: {pkg.manifest.trigger_examples}\n"
            f"Should NOT fire for: {pkg.manifest.trigger_counter_examples}\n"
            f"Task: {task_text}")
        try:
            raw = self._complete(prompt)
            score = float(json.loads(raw)["score"])
        except Exception:
            score = 0.0
        return ScoredSkill(pkg.name, round(score, 4), {"stage1": round(stage1, 3)})


_PIN_RE = re.compile(r"use the ([a-z0-9-]+) skill", re.I)


class Resolver:
    def __init__(self, library, reranker=None, max_active: int = MAX_ACTIVE,
                 threshold: float = FIRE_THRESHOLD):
        self.library = library
        self.reranker = reranker or DeterministicReranker()
        self.max_active = max_active
        self.threshold = threshold

    # -- stage 1 ---------------------------------------------------------------
    def _stage1(self, task_text: str) -> dict[str, float]:
        q_tokens = set(tokens(task_text))
        q_emb = _embed(task_text)
        scores = {}
        for pkg in self.library.all():
            meta = " ".join([pkg.name.replace("-", " "), pkg.description]
                            + pkg.manifest.trigger_examples)
            bm = _overlap(q_tokens, set(tokens(meta)))
            emb = max(0.0, _cosine(q_emb, _embed(meta)))
            scores[pkg.name] = 0.5 * bm + 0.5 * emb
        return scores

    # -- full resolution ---------------------------------------------------------
    def resolve(self, task_text: str, provider_capabilities=frozenset(),
                pins: tuple = ()) -> Resolution:
        log: list[str] = []
        excluded: list[tuple[str, str]] = []
        pins = list(pins)
        m = _PIN_RE.search(task_text or "")
        if m and m.group(1) not in pins:
            pins.append(m.group(1))

        stage1 = self._stage1(task_text)
        ranked = sorted(stage1.items(), key=lambda kv: -kv[1])[:SHORTLIST_K]
        log.append(f"stage1 shortlist: {[n for n, _ in ranked]}")

        scored: dict[str, ScoredSkill] = {}
        for name, s1 in ranked:
            pkg = self.library.get(name)
            scored[name] = self.reranker.score(pkg, task_text, s1)

        shadow_hits: list[ScoredSkill] = []
        fired: list[ScoredSkill] = []
        for name, sc in sorted(scored.items(), key=lambda kv: -kv[1].score):
            pkg = self.library.get(name)
            reason = None
            if name in pins:
                fired.append(sc)
                log.append(f"pin: {name} forced active (score {sc.score})")
                continue
            if pkg.lifecycle == "shadow":
                if sc.score >= self.threshold:
                    shadow_hits.append(sc)
                    log.append(f"shadow: {name} scored {sc.score} — logged, "
                               "not governing (shadow state)")
                continue
            if pkg.lifecycle != "active":
                reason = f"lifecycle is {pkg.lifecycle} (only active skills govern)"
            elif sc.score < self.threshold:
                reason = (f"score {sc.score} below threshold {self.threshold} "
                          f"(example {sc.detail.get('example')}, counter "
                          f"{sc.detail.get('counter')})")
            else:
                missing = [c for c in pkg.manifest.requires_capabilities
                           if c not in provider_capabilities]
                if missing:
                    reason = (f"requires capabilities the bound provider "
                              f"lacks: {missing}")
            if reason:
                excluded.append((name, reason))
                log.append(f"excluded: {name} — {reason}")
            else:
                fired.append(sc)
                log.append(f"fired: {name} score {sc.score} {sc.detail}")

        # conflicts: deterministic resolution by specificity (score)
        kept: list[ScoredSkill] = []
        for sc in fired:
            pkg = self.library.get(sc.name)
            loser = None
            for other in kept:
                opkg = self.library.get(other.name)
                if sc.name in opkg.manifest.conflicts or \
                        other.name in pkg.manifest.conflicts:
                    loser = other if other.score < sc.score else sc
                    winner = sc if loser is other else other
                    excluded.append((loser.name,
                                     f"conflicts with {winner.name}; "
                                     f"{winner.name} wins on specificity "
                                     f"({winner.score} vs {loser.score})"))
                    log.append(f"conflict: {loser.name} dropped in favour "
                               f"of {winner.name}")
                    if loser is sc:
                        break
                    kept.remove(other)
                    kept.append(sc)
                    break
            else:
                kept.append(sc)
        fired = kept

        # capability gate also applies to pinned skills (a pin cannot
        # conjure a capability the provider does not have) — but the
        # failure is surfaced, never silent.
        final: list[ScoredSkill] = []
        for sc in fired:
            pkg = self.library.get(sc.name)
            missing = [c for c in pkg.manifest.requires_capabilities
                       if c not in provider_capabilities]
            if missing and sc.name not in pins:
                excluded.append((sc.name, f"requires capabilities {missing}"))
            else:
                if missing:
                    log.append(f"WARNING: pinned {sc.name} lacks capabilities "
                               f"{missing} on this provider — proceeding "
                               "because the user pinned it")
                final.append(sc)

        if len(final) > self.max_active:
            for sc in final[self.max_active:]:
                excluded.append((sc.name, f"over co-active cap K={self.max_active}"))
            final = final[:self.max_active]

        primary = None
        if pins:
            primary = next((p for p in pins if p in [s.name for s in final]), None)
        if primary is None and final:
            primary = final[0].name
        return Resolution(active=final, primary=primary,
                          shadow_hits=shadow_hits, excluded=excluded, log=log)
