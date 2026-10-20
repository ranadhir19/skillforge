"""Episode storage: every run becomes a mineable episode.

Design Part 3.4 is explicit that the Phase 2 learning loop must never
learn from its own outputs unmediated: it learns from *episodes* —
(trajectory, outcome) pairs whose outcomes were labelled by
deterministic verifiers or by humans, not by the model that produced
them. This store is that structure, ready now: each episode records
the task and its *shape* (the clustering signature the miner will
group by), the skills used, the plan hash, per-step trace statuses,
the verifier-labelled outcome (or ``None`` when no verifier ran —
never silently treated as success), and the cost. Storage is an
append-only JSONL file: boring, greppable, replayable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def task_shape(task_text: str, actions: list, skills: list) -> str:
    """Clustering signature for later mining: action pattern + skill
    set + the task's content keywords (stopword-light, sorted)."""
    words = [w for w in _TOKEN_RE.findall(task_text.lower())
             if len(w) > 3]
    keywords = sorted(set(words))[:6]
    sig = "|".join(sorted(actions)) + "::" + "|".join(sorted(skills)) \
        + "::" + ",".join(keywords)
    return hashlib.sha256(sig.encode()).hexdigest()[:12]


class EpisodeStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def append(self, episode: dict) -> dict:
        episode = dict(episode)
        episode.setdefault("episode_id",
                           f"ep-{int(time.time() * 1000)}-"
                           f"{hashlib.sha256(json.dumps(episode, sort_keys=True, default=str).encode()).hexdigest()[:6]}")
        episode.setdefault("recorded_at", time.time())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(episode, sort_keys=True, default=str) + "\n")
        return episode

    def all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def by_skill(self, name: str) -> list[dict]:
        return [e for e in self.all() if name in e.get("skills_used", [])]

    def by_shape(self, shape: str) -> list[dict]:
        return [e for e in self.all() if e.get("shape") == shape]

    def shapes(self) -> dict:
        """shape -> count, the miner's first view of the world."""
        counts: dict[str, int] = {}
        for e in self.all():
            counts[e.get("shape", "?")] = counts.get(e.get("shape", "?"), 0) + 1
        return counts
