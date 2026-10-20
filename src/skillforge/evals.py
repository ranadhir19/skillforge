"""The eval runner: behaviour, verified deterministically.

Two case kinds (design Part 3.3 — a candidate never writes its own
exam, so suites ship *in* the package but are executed by the platform
against fixtures the package does not control):

- ``trigger`` cases: resolve the case task against the *whole
  library* and check this skill fired (or did not). This is trigger
  regression by construction — every skill's suite runs against every
  other skill's presence.
- ``task`` cases: run a structured task end-to-end with this skill
  pinned, then check the artifact with deterministic assertions
  (required/forbidden strings, regexes, declared sections, minimum
  length, corpus-value placeholders like ``{corpus:revenue_all}``) and,
  when the package ships ``evals/verifiers.py``, its custom
  ``verify(case, artifact, ctx)`` hook.

Holdout cases (``holdout: true``) are reported separately, always.
"""

from __future__ import annotations

import importlib.util
import os
import re
import tempfile

import yaml

from .corpus import TOTALS, TaskSpec


def _subst(text: str) -> str:
    def rep(m):
        key = m.group(1)
        if key in TOTALS:
            v = TOTALS[key]
            return f"{v:.2f}" if isinstance(v, float) else str(v)
        return m.group(0)
    return re.sub(r"\{corpus:([a-z_0-9]+)\}", rep, text)


class CaseResult:
    def __init__(self, case_id: str, kind: str, passed: bool, detail: str,
                 holdout: bool = False):
        self.case_id = case_id
        self.kind = kind
        self.passed = passed
        self.detail = detail
        self.holdout = holdout

    def to_dict(self):
        return vars(self).copy()


class EvalReport:
    def __init__(self, skill: str, provider: str):
        self.skill = skill
        self.provider = provider
        self.results: list[CaseResult] = []

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def holdout_results(self) -> list:
        return [r for r in self.results if r.holdout]

    def to_dict(self) -> dict:
        return {"skill": self.skill, "provider": self.provider,
                "total": self.total, "passed": self.passed,
                "pass_rate": round(self.pass_rate, 4),
                "results": [r.to_dict() for r in self.results]}


def load_cases(pkg) -> list[dict]:
    cases: list[dict] = []
    for rel, is_holdout in ((pkg.manifest.evals_suite, False),
                            (pkg.manifest.evals_holdout, True)):
        if not rel:
            continue
        path = os.path.join(pkg.path, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for case in data.get("cases", []):
            case = dict(case)
            if is_holdout:
                case["holdout"] = True
            cases.append(case)
    return cases


def _load_verifier(pkg):
    path = os.path.join(pkg.path, "evals", "verifiers.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(
        f"verifiers_{pkg.name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "verify", None)


def check_expectations(case: dict, artifact: str) -> tuple[bool, str]:
    exp = case.get("expect") or {}
    problems = []
    for s in exp.get("contains_all", []) or []:
        if _subst(str(s)) not in artifact:
            problems.append(f"missing required text: {s!r}")
    for s in exp.get("contains_none", []) or []:
        if _subst(str(s)) in artifact:
            problems.append(f"forbidden text present: {s!r}")
    for pat in exp.get("regex", []) or []:
        if not re.search(_subst(str(pat)), artifact, re.M):
            problems.append(f"regex not matched: {pat!r}")
    for sec in exp.get("sections", []) or []:
        if f"## {sec}" not in artifact:
            problems.append(f"missing section: ## {sec}")
    if exp.get("min_chars") and len(artifact) < int(exp["min_chars"]):
        problems.append(f"artifact too short: {len(artifact)} < {exp['min_chars']}")
    return (not problems), "; ".join(problems) if problems else "expectations met"


class EvalRunner:
    """Executes packages' suites. ``platform`` supplies resolve/run."""

    def __init__(self, platform):
        self.platform = platform

    def run_package(self, pkg, provider: str = "stub-pro",
                    kinds: tuple = ("trigger", "task")) -> EvalReport:
        report = EvalReport(pkg.name, provider)
        caps = self.platform.provider_capabilities(provider)
        cases = load_cases(pkg)
        for case in cases:
            kind = case.get("kind")
            if kind not in kinds:
                continue
            if kind == "trigger":
                res = self._trigger_case(pkg, case, caps)
            else:
                res = self._task_case(pkg, case, provider)
            report.results.append(res)
        return report

    def _trigger_case(self, pkg, case, caps) -> CaseResult:
        from .resolver import Resolver
        resolver = Resolver(self.platform.library)
        resolution = resolver.resolve(case["task"], provider_capabilities=caps)
        fired = pkg.name in resolution.names()
        # A shadow/imported package cannot fire by design; for its own
        # suite, "would fire" = scored at/above threshold. Evaluate the
        # score directly so suites are meaningful pre-promotion.
        if pkg.lifecycle != "active":
            sc = resolver.reranker.score(
                pkg, case["task"],
                resolver._stage1(case["task"]).get(pkg.name, 0.0))
            fired = sc.score >= resolver.threshold
        ok = fired == bool(case["should_fire"])
        return CaseResult(case["id"], "trigger", ok,
                          f"fired={fired} expected={case['should_fire']}",
                          holdout=bool(case.get("holdout")))

    def _task_case(self, pkg, case, provider) -> CaseResult:
        spec_d = case["task"]
        task = TaskSpec(
            task_id=f"eval-{pkg.name}-{case['id']}",
            goal=spec_d["goal"],
            sub_questions=spec_d.get("sub_questions", []),
            lookups=spec_d.get("lookups", []),
            computations=spec_d.get("computations", []),
            script_steps=spec_d.get("script_steps", []),
            title=spec_d.get("title", "Deliverable"),
            publish_to=spec_d.get("publish_to"),
            skill_hint=pkg.name)
        with tempfile.TemporaryDirectory(prefix="skillforge-eval-") as sandbox:
            bundle = self.platform.run_task(
                task, provider=provider, pins=(pkg.name,),
                sandbox_dir=sandbox, record_episode=False)
            record = bundle["record"]
            artifact = record.final_output
            ok, detail = check_expectations(case, artifact)
            if record.status != "completed" and not case.get("allow_partial"):
                ok = False
                detail = f"run status {record.status}; {detail}"
            verifier = _load_verifier(pkg)
            if verifier is not None:
                vok, vdetail = verifier(case, artifact,
                                        {"record": record, "totals": TOTALS})
                if not vok:
                    ok = False
                    detail = f"{detail}; verifier: {vdetail}"
            return CaseResult(case["id"], "task", ok,
                              detail or "ok",
                              holdout=bool(case.get("holdout")))
