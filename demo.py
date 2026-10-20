"""SkillForge end-to-end demo (seeded, deterministic, offline).

A full platform session:
  1. the starter library loads and every package validates,
  2. a task arrives; the resolver picks its skills (with reasons),
     the planner composes a governed DAG, the runtime executes it —
     the publish step passes through data-analysis's approval gate,
  3. the same task with the approver *denying* publish,
  4. the same task on the basic provider tier (the precision gap is
     the tier's documented property, shown not hidden),
  5. a vanilla SKILL.md-only folder is imported with safe defaults,
  6. a NEW skill is created dynamically from a demonstration —
     drafted, validated, trialled, approved at the gate, registered
     as shadow (it is seen but does not govern), promoted, and then
     governing a real run.

Writes results/demo_run.json. Scratch work (imports, creation)
happens in a copied library so the starter library stays pristine.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from skillforge import Platform, TaskSpec, repo_platform
from skillforge.corpus import TOTALS, demo_task
from skillforge.validate_pkg import validate_package

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")


def show(bundle, label):
    rec = bundle["record"]
    print(f"  [{label}] status={rec.status} tokens={rec.total_tokens} "
          f"cost=${rec.total_cost_usd:.4f} plan={rec.plan.plan_hash()}")
    for t in rec.traces:
        print(f"    [{t.status:16s}] {t.step_id:12s} action={t.action:10s} "
              f"skill={t.skill or '-':28s} provider={t.provider}")
    return rec


def main():
    os.makedirs(RESULTS, exist_ok=True)
    plat = repo_platform(HERE)
    print("== 1. Starter library ==")
    reports = {p.name: validate_package(p.path) for p in plat.library.all()}
    valid = sum(1 for r in reports.values() if r.valid)
    print(f"  {len(reports)} skills loaded, {valid} statically valid")

    task = demo_task()
    print("\n== 2. Governed run (publish approved at the gate) ==")
    for line in plat.resolver.resolve(
            task.goal, provider_capabilities=plat.provider_capabilities("stub-pro"),
            pins=(task.skill_hint,)).log[:4]:
        print(f"  resolver: {line}")
    bundle = plat.run_task(task, provider="stub-pro")
    rec = show(bundle, "approved")
    ok = f"{TOTALS['net_revenue']:.2f}" in rec.final_output
    print(f"  verifier: net revenue {TOTALS['net_revenue']:.2f} present: {ok}")

    print("\n== 3. Same task, approver denies publish ==")
    denied = plat.run_task(task, provider="stub-pro",
                           approver=lambda step, r: step.action != "publish",
                           record_episode=False)
    show(denied, "denied")

    print("\n== 4. Same task on the basic tier (documented precision gap) ==")
    basic = plat.run_task(task, provider="stub-basic", record_episode=False)
    show(basic, "basic")
    exact = f"{TOTALS['net_revenue']:.2f}" in basic["record"].final_output
    print(f"  exact net revenue present on basic tier: {exact} "
          "(expected False — the tier rounds decimal operands; the pro "
          "run in step 2 carries the exact figure)")

    print("\n== 5. Vanilla import (SKILL.md only, safe defaults) ==")
    scratch = tempfile.mkdtemp(prefix="skillforge-demo-")
    lib_root = os.path.join(scratch, "library")
    shutil.copytree(os.path.join(HERE, "library"), lib_root)
    vanilla_dir = os.path.join(scratch, "plain-skill")
    os.makedirs(vanilla_dir)
    with open(os.path.join(vanilla_dir, "SKILL.md"), "w") as fh:
        fh.write("---\nname: plain-skill\ndescription: Summarise a text in "
                 "three bullet points.\n---\n\n# plain-skill\n\nRead the "
                 "text. Write three bullet points.\n")
    plat2 = Platform([lib_root], os.path.join(scratch, "data"))
    result = plat2.library.import_package(vanilla_dir)
    print(f"  imported as lifecycle={result['lifecycle']}")
    for line in result["permission_diff"]["summary_lines"]:
        print(f"    {line}")

    print("\n== 6. Dynamic creation: unit-economics-snapshot ==")
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
    created = plat2.creator().create(
        description="Compute a unit-economics snapshot for a quarter: "
                    "totals, then revenue per unit and cost per unit.",
        demonstration=demonstration)
    print(f"  creation: ok={created.ok} stage={created.stage} "
          f"lifecycle={created.lifecycle} trial="
          f"{created.trial['passed']}/{created.trial['total']}")
    ue_task = TaskSpec(task_id="ue-demo",
                       goal="Give me the unit-economics snapshot for Q1",
                       lookups=demonstration["task_spec"]["lookups"],
                       computations=demonstration["task_spec"]["computations"],
                       title="Unit-economics snapshot Q1")
    shadow = plat2.run_task(ue_task, record_episode=False)
    print(f"  while shadow: primary={shadow['resolution'].primary} "
          f"shadow_hits={[s.name for s in shadow['resolution'].shadow_hits]}")
    plat2.library.set_lifecycle("unit-economics-snapshot", "active",
                                actor="demo")
    active = plat2.run_task(ue_task, record_episode=False)
    show(active, "created skill governing")
    print(f"  per-unit figures in output: rev/unit={rev} cost/unit={cpu} "
          f"present: {rev in active['record'].final_output and cpu in active['record'].final_output}")

    payload = {
        "task": task.task_id,
        "approved_run": bundle["record"].to_dict(),
        "denied_status": denied["record"].status,
        "basic_status": basic["record"].status,
        "creation": created.to_dict(),
        "episodes_in_store": len(plat.episodes.all()),
        "audit_chain_valid": plat.audit.verify_chain(),
    }
    with open(os.path.join(RESULTS, "demo_run.json"), "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\nwrote results/demo_run.json; episodes recorded: "
          f"{payload['episodes_in_store']}; audit chain valid: "
          f"{payload['audit_chain_valid']}")


if __name__ == "__main__":
    main()
