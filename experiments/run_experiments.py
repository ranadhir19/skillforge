"""Experiments: the numbers in results/results.md, from real runs.

E1  Trigger quality: every trigger case in the library (40 positive,
    40 near-miss counter-examples) resolved against the whole library.
E2  Eval pass matrix: all 100 cases on both offline tiers.
E3  Gate behaviour: publish approved vs denied (run status + traces).
E4  Dynamic creation: the full Phase 1 flow, measured.
E5  Vanilla import: a SKILL.md-only folder through import + promotion.

Writes results/results.md and results/experiments.json. Deterministic.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillforge import Platform, TaskSpec, repo_platform
from skillforge.corpus import TOTALS, demo_task
from skillforge.evals import load_cases

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, "results")


def e1_trigger_quality(plat) -> dict:
    ev = plat.evaluator()
    tp = fp = fn = tn = 0
    per_skill = {}
    for pkg in plat.library.all():
        expected = {c["id"]: bool(c["should_fire"])
                    for c in load_cases(pkg) if c["kind"] == "trigger"}
        rep = ev.run_package(pkg, kinds=("trigger",))
        s = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for r in rep.results:
            want = expected[r.case_id]
            key = ("tp" if r.passed else "fn") if want else \
                  ("tn" if r.passed else "fp")
            s[key] += 1
        per_skill[pkg.name] = s
        tp += s["tp"]; fp += s["fp"]; fn += s["fn"]; tn += s["tn"]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "per_skill": per_skill}


def e2_eval_matrix(plat) -> dict:
    ev = plat.evaluator()
    out = {}
    for provider in ("stub-pro", "stub-basic"):
        total = passed = 0
        failing = []
        for pkg in plat.library.all():
            rep = ev.run_package(pkg, provider=provider)
            total += rep.total
            passed += rep.passed
            for r in rep.results:
                if not r.passed:
                    failing.append(f"{pkg.name}/{r.case_id}")
        out[provider] = {"total": total, "passed": passed,
                         "pass_rate": round(passed / total, 4),
                         "failing": failing}
    return out


def e3_gates(plat) -> dict:
    approved = plat.run_task(demo_task(), provider="stub-pro",
                             record_episode=False)
    denied = plat.run_task(demo_task(), provider="stub-pro",
                           approver=lambda s, r: s.action != "publish",
                           record_episode=False)
    return {"approved_status": approved["record"].status,
            "denied_status": denied["record"].status,
            "denied_publish_trace": [t.status for t in denied["record"].traces
                                     if t.step_id == "publish"]}


def e4_creation() -> dict:
    scratch = tempfile.mkdtemp(prefix="skillforge-exp-")
    lib_root = os.path.join(scratch, "library")
    shutil.copytree(os.path.join(ROOT, "library"), lib_root)
    plat = Platform([lib_root], os.path.join(scratch, "data"))
    rev = f"{TOTALS['revenue_all'] / TOTALS['units_all']:.2f}"
    cpu = f"{TOTALS['costs_all'] / TOTALS['units_all']:.2f}"
    demonstration = {
        "name": "unit-economics-snapshot",
        "task": "Give me the unit-economics snapshot for Q1",
        "steps": ["Look up total revenue, total costs and units sold.",
                  "Compute revenue per unit and cost per unit.",
                  "Write the snapshot: totals first, then per-unit figures."],
        "sections": ["Totals", "Per-unit figures", "Notes"],
        "lookups": [1], "computations": [1],
        "task_spec": {
            "goal": "Unit-economics snapshot for Q1 2026",
            "lookups": [{"label": "total revenue", "metric": "revenue_usd"},
                        {"label": "total costs", "metric": "costs_usd"},
                        {"label": "units sold", "metric": "units"}],
            "computations": [
                {"label": "revenue per unit",
                 "expression": "{total revenue} / {units sold}", "refs": True},
                {"label": "cost per unit",
                 "expression": "{total costs} / {units sold}", "refs": True}],
            "title": "Unit-economics snapshot Q1"},
        "expect": {"sections": ["Totals", "Per-unit figures", "Notes"],
                   "contains_all": ["{corpus:revenue_all}", rev, cpu]},
    }
    t0 = time.time()
    res = plat.creator().create(
        description="Compute a unit-economics snapshot for a quarter: "
                    "totals, then revenue per unit and cost per unit.",
        demonstration=demonstration)
    elapsed = round(time.time() - t0, 2)
    task = TaskSpec(task_id="ue-exp",
                    goal="Give me the unit-economics snapshot for Q1",
                    lookups=demonstration["task_spec"]["lookups"],
                    computations=demonstration["task_spec"]["computations"],
                    title="Unit-economics snapshot Q1")
    shadow = plat.run_task(task, record_episode=False)
    plat.library.set_lifecycle("unit-economics-snapshot", "active", actor="exp")
    active = plat.run_task(task, record_episode=False)
    return {"ok": res.ok, "stage": res.stage, "lifecycle": res.lifecycle,
            "trial": f"{res.trial['passed']}/{res.trial['total']}",
            "seconds": elapsed,
            "shadow_primary": shadow["resolution"].primary,
            "shadow_hits": [s.name for s in shadow["resolution"].shadow_hits],
            "active_primary": active["resolution"].primary,
            "active_status": active["record"].status,
            "figures_verified": rev in active["record"].final_output
            and cpu in active["record"].final_output}


def e5_vanilla_import() -> dict:
    scratch = tempfile.mkdtemp(prefix="skillforge-exp5-")
    lib_root = os.path.join(scratch, "library")
    os.makedirs(lib_root)
    pkg_dir = os.path.join(scratch, "plain-skill")
    os.makedirs(pkg_dir)
    with open(os.path.join(pkg_dir, "SKILL.md"), "w") as fh:
        fh.write("---\nname: plain-skill\ndescription: Summarise a text in "
                 "three bullet points.\n---\n\n# plain-skill\n\nRead the "
                 "text. Write three bullet points.\n")
    plat = Platform([lib_root], os.path.join(scratch, "data"))
    result = plat.library.import_package(pkg_dir)
    return {"lifecycle": result["lifecycle"],
            "valid": result["validation"]["valid"],
            "warnings": len(result["validation"]["warnings"]),
            "permissions": result["permission_diff"]["summary_lines"]}


def main():
    os.makedirs(RESULTS, exist_ok=True)
    plat = repo_platform(ROOT)
    data = {"E1_trigger_quality": e1_trigger_quality(plat),
            "E2_eval_matrix": e2_eval_matrix(plat),
            "E3_gates": e3_gates(plat),
            "E4_creation": e4_creation(),
            "E5_vanilla_import": e5_vanilla_import()}
    with open(os.path.join(RESULTS, "experiments.json"), "w") as fh:
        json.dump(data, fh, indent=2)

    e1, e2, e3, e4, e5 = (data["E1_trigger_quality"], data["E2_eval_matrix"],
                          data["E3_gates"], data["E4_creation"],
                          data["E5_vanilla_import"])
    lines = [
        "# SkillForge — experiment results",
        "",
        "All numbers from actual runs of this code against the seeded",
        "fixtures (`src/skillforge/corpus.py`), via",
        "`experiments/run_experiments.py`. Offline tiers only.",
        "",
        "## E1 — Trigger quality (whole-library regression)",
        "",
        f"80 trigger cases (40 examples that should fire, 40 near-miss",
        f"counter-examples that should not), each resolved against the",
        f"full 20-skill library: TP={e1['tp']} FP={e1['fp']} "
        f"FN={e1['fn']} TN={e1['tn']};",
        f"precision {e1['precision']}, recall {e1['recall']}.",
        "",
        "## E2 — Eval pass matrix (100 cases: trigger + task, per skill)",
        "",
        f"- stub-pro:   {e2['stub-pro']['passed']}/{e2['stub-pro']['total']} "
        f"({e2['stub-pro']['pass_rate']})",
        f"- stub-basic: {e2['stub-basic']['passed']}/{e2['stub-basic']['total']} "
        f"({e2['stub-basic']['pass_rate']}); failing: "
        f"{', '.join(e2['stub-basic']['failing']) or 'none'}",
        "",
        "The basic tier's failures are its documented strategy property",
        "(it rounds decimal operands before computing), surfacing in",
        "exact-figure task cases — a measured capability difference,",
        "not noise: trigger behaviour is identical across tiers.",
        "",
        "## E3 — Approval gate",
        "",
        f"Demo task with publish approved: run status "
        f"`{e3['approved_status']}`. With the approver denying publish:",
        f"`{e3['denied_status']}` (publish trace: "
        f"{e3['denied_publish_trace']}). The analysis completes; the",
        "publish does not happen.",
        "",
        "## E4 — Dynamic creation (Phase 1 flow)",
        "",
        f"Created `unit-economics-snapshot` from a description + one",
        f"demonstration: ok={e4['ok']}, registered as `{e4['lifecycle']}`,",
        f"trial {e4['trial']} passed, flow took {e4['seconds']}s.",
        f"As shadow, a matching task resolved with primary="
        f"{e4['shadow_primary']} and shadow_hits={e4['shadow_hits']} —",
        "seen, logged, not governing. After promotion to active, the",
        f"same task ran under it (primary={e4['active_primary']}, status",
        f"{e4['active_status']}) and its output carried the verified",
        f"per-unit figures ({e4['figures_verified']}).",
        "",
        "## E5 — Vanilla import",
        "",
        f"A SKILL.md-only folder imported with synthesised safe",
        f"defaults: lifecycle `{e5['lifecycle']}`, static validation",
        f"valid={e5['valid']} with {e5['warnings']} warning(s).",
        "Permission summary at import:",
        "",
    ]
    lines += [f"- {line}" for line in e5["permissions"]]
    lines += ["", "## Honest limits", "",
              "- The offline tiers execute a step's procedure *structure*",
              "  (tools, sections, gates); following skill prose",
              "  *semantically* is what a keyed model does through the",
              "  same seam — unmeasured here because it needs keys.",
              "- Trigger quality is measured against the library's own",
              "  authored cases (positives + authored near-misses), not",
              "  an external benchmark.",
              ""]
    with open(os.path.join(RESULTS, "results.md"), "w") as fh:
        fh.write("\n".join(lines))
    print(json.dumps({k: (v if not isinstance(v, dict) else
                            {kk: vv for kk, vv in v.items()
                             if kk != "per_skill"})
                      for k, v in data.items()}, indent=2))


if __name__ == "__main__":
    main()
