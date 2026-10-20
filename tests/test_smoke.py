"""Core tests: packages, validator, library, resolver, runtime governance.

The library-level behavioural suites (every starter skill's evals,
end-to-end) live in test_library.py; creation in test_creation.py;
the server in test_server.py.
"""

from __future__ import annotations

import os
import sys
import zipfile

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillforge import (Library, Platform, ScriptedProvider, TaskSpec,
                        load_package, validate_package)
from skillforge.corpus import CHUNKS, METRIC_ROWS, TOTALS, demo_task
from skillforge.runtime import ManagedRuntime
from skillforge.registry import default_registry

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_ROOT = os.path.join(ROOT, "library")

EXPECTED_SKILLS = [
    "code-review", "data-analysis", "deploy-checklist", "diagnosing-bugs",
    "document-drafting", "fix-failing-ci", "frontend-design", "grill-me",
    "handoff", "improve-codebase-architecture", "internal-comms",
    "pdf-extract-and-fill", "postgres-best-practices",
    "resolve-merge-conflict", "skill-creator", "spreadsheet-analysis",
    "test-driven-development", "verification-before-completion",
    "web-research", "webapp-testing",
]


@pytest.fixture()
def platform(tmp_path):
    return Platform([LIB_ROOT], str(tmp_path / "data"))


def _write_pkg(tmp_path, name, manifest_overrides=None, body="Do the thing.",
               description="A test skill for tests.", extra_files=None,
               frontmatter_name=None):
    root = tmp_path / name
    (root / "evals").mkdir(parents=True)
    fm = {"name": frontmatter_name or name, "description": description}
    with open(root / "SKILL.md", "w") as fh:
        fh.write("---\n")
        yaml.safe_dump(fm, fh)
        fh.write("---\n\n# " + name + "\n\n" + body + "\n")
    manifest = {
        "apiVersion": "skillforge/v1", "name": name, "version": "0.1.0",
        "lifecycle": "active",
        "triggers": {"examples": ["do the test thing"],
                     "counter_examples": ["do something else entirely"]},
        "requires": {"tools": ["native:calculator"], "capabilities": [],
                     "min_context_tokens": 0},
        "permissions": {"tools": ["native:calculator"], "scripts": [],
                        "network": "none",
                        "filesystem": {"read": [], "write": [""]},
                        "approval_required_for": []},
        "composition": {"composes": [], "conflicts": []},
        "governs": ["compute"],
        "output": {"sections": []},
        "budget": {"max_tokens_per_run": None, "max_script_seconds": None},
        "evals": {"suite": "evals/cases.yaml", "holdout": None, "min_pass": 0.9},
    }
    manifest.update(manifest_overrides or {})
    with open(root / "skill.yaml", "w") as fh:
        yaml.safe_dump(manifest, fh)
    with open(root / "evals" / "cases.yaml", "w") as fh:
        yaml.safe_dump({"cases": [
            {"id": "t1", "kind": "trigger", "task": "do the test thing",
             "should_fire": True}]}, fh)
    for rel, content in (extra_files or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return root


# ---------------------------------------------------------------- packages

def test_starter_library_complete_and_valid():
    lib = Library([LIB_ROOT])
    assert lib.names() == EXPECTED_SKILLS
    assert not lib.load_errors
    for pkg in lib.all():
        rep = validate_package(pkg.path)
        assert rep.valid, f"{pkg.name}: {rep.errors}"
        assert pkg.lifecycle == "active"


def test_vanilla_package_gets_safe_defaults(tmp_path):
    root = tmp_path / "plain-skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: plain-skill\ndescription: A plain agent skill.\n---\n\n"
        "# plain-skill\n\nFollow these steps.\n")
    pkg = load_package(str(root))
    assert pkg.manifest.native is False
    assert pkg.lifecycle == "imported"
    assert pkg.manifest.perm_network == "none"
    assert pkg.manifest.perm_scripts == []
    rep = validate_package(str(root))
    assert rep.valid  # warnings only


def test_validator_rejects_name_mismatch(tmp_path):
    root = _write_pkg(tmp_path, "some-skill", frontmatter_name="other-skill")
    rep = validate_package(str(root))
    assert not rep.valid
    assert any("does not match" in e or "!=" in e for e in rep.errors)


def test_validator_rejects_undeclared_script(tmp_path):
    root = _write_pkg(tmp_path, "scripty", extra_files={
        "scripts/sneaky.py": "print('hi')\n"})
    rep = validate_package(str(root))
    assert not rep.valid
    assert any("not in permissions.scripts" in e for e in rep.errors)


def test_validator_rejects_missing_eval_suite(tmp_path):
    root = _write_pkg(tmp_path, "no-evals")
    os.remove(root / "evals" / "cases.yaml")
    rep = validate_package(str(root))
    assert not rep.valid
    assert any("missing" in e for e in rep.errors)


def test_validator_rejects_bad_lifecycle_and_capability(tmp_path):
    root = _write_pkg(tmp_path, "bad-state", manifest_overrides={
        "lifecycle": "live",
        "requires": {"tools": [], "capabilities": ["telepathy"],
                     "min_context_tokens": 0}})
    rep = validate_package(str(root))
    assert not rep.valid
    assert any("lifecycle" in e for e in rep.errors)
    assert any("capability" in e for e in rep.errors)


# ---------------------------------------------------------------- library io

def test_import_export_roundtrip(tmp_path):
    src = Platform([LIB_ROOT], str(tmp_path / "d1"))
    zip_path = str(tmp_path / "da.zip")
    src.library.export_package("data-analysis", zip_path, portable=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith("/SKILL.md") for n in names)
    # portable export strips the manifest and provenance
    assert not any(n.endswith("skill.yaml") for n in names)
    assert not any(n.endswith("provenance.json") for n in names)
    assert any(n.endswith("/EXPORT_NOTE.md") for n in names)

    dest_root = tmp_path / "lib2"
    dest_root.mkdir()
    plat2 = Platform([str(dest_root)], str(tmp_path / "d2"))
    result = plat2.library.import_package(zip_path)
    assert result["skill"] == "data-analysis"
    assert result["lifecycle"] == "imported"  # vanilla after portable export
    assert any("Network: none" in line
               for line in result["permission_diff"]["summary_lines"])


def test_lifecycle_change_is_audited(platform):
    import shutil
    work = os.path.join(platform.data_dir, "libcopy")
    shutil.copytree(LIB_ROOT, work)
    plat = Platform([work], os.path.join(platform.data_dir, "d3"))
    plat.library.set_lifecycle("grill-me", "deprecated", actor="tester")
    assert plat.library.get("grill-me").lifecycle == "deprecated"
    assert plat.audit.verify_chain()
    events = [e for e in plat.audit.entries() if e["event"] == "lifecycle"]
    assert events and events[-1]["payload"]["skill"] == "grill-me"


# ---------------------------------------------------------------- resolver

def test_resolver_fires_primary_and_explains_exclusions(platform):
    caps = ScriptedProvider.CAPABILITIES["stub-pro"]
    res = platform.resolver.resolve(
        "Analyse Q1 revenue — totals, North region, costs and net",
        provider_capabilities=caps)
    assert res.primary == "data-analysis"
    assert "data-analysis" in res.names()
    assert all(reason for _name, reason in res.excluded)


def test_resolver_counter_example_suppresses(platform):
    caps = ScriptedProvider.CAPABILITIES["stub-pro"]
    res = platform.resolver.resolve("What is our refund policy?",
                                    provider_capabilities=caps)
    assert "data-analysis" not in res.names()


def test_resolver_pin_wins(platform):
    caps = ScriptedProvider.CAPABILITIES["stub-pro"]
    res = platform.resolver.resolve(
        "Summarise the handbook pages", provider_capabilities=caps,
        pins=("document-drafting",))
    assert res.primary == "document-drafting"


def test_resolver_capability_gate(tmp_path):
    root = _write_pkg(tmp_path, "vision-skill", manifest_overrides={
        "requires": {"tools": [], "capabilities": ["vision"],
                     "min_context_tokens": 0}})
    plat = Platform([str(tmp_path)], str(tmp_path / "data"))
    basic = plat.resolver.resolve(
        "do the test thing",
        provider_capabilities=ScriptedProvider.CAPABILITIES["stub-basic"])
    assert "vision-skill" not in basic.names()
    assert any("capabilit" in reason for _n, reason in basic.excluded)
    pro = plat.resolver.resolve(
        "do the test thing",
        provider_capabilities=ScriptedProvider.CAPABILITIES["stub-pro"])
    assert "vision-skill" in pro.names()


def test_conflict_resolution_is_deterministic(platform):
    caps = ScriptedProvider.CAPABILITIES["stub-pro"]
    res = platform.resolver.resolve(
        "Write a handoff for the on-call engineer about the payments "
        "outage, and an update for stakeholders",
        provider_capabilities=caps)
    both = {"handoff", "internal-comms"} & set(res.names())
    assert len(both) <= 1  # declared conflict: at most one governs


# ---------------------------------------------------------------- runtime

def test_demo_task_completes_and_publishes(platform):
    bundle = platform.run_task(demo_task(), provider="stub-pro")
    rec = bundle["record"]
    assert rec.status == "completed"
    assert bundle["resolution"].primary == "data-analysis"
    out = rec.final_output
    assert f"{TOTALS['revenue_all']:.2f}" in out
    assert f"{TOTALS['net_revenue']:.2f}" in out
    sandbox_file = os.path.join(platform.sandbox_dir, "q1-revenue-analysis.md")
    assert os.path.exists(sandbox_file)
    assert all(t.skill == "data-analysis" for t in rec.traces)


def test_approval_gate_denial_blocks_publish(platform):
    bundle = platform.run_task(
        demo_task(), provider="stub-pro",
        approver=lambda step, record: step.action != "publish")
    rec = bundle["record"]
    assert rec.status == "blocked_approval"
    publish = [t for t in rec.traces if t.step_id == "publish"]
    assert publish and publish[0].status == "denied"


def test_permission_denied_when_skill_lacks_tool(tmp_path):
    # governs compute but grants only doc_search -> compute is refused
    _write_pkg(tmp_path, "no-calc", manifest_overrides={
        "requires": {"tools": ["native:doc_search"], "capabilities": [],
                     "min_context_tokens": 0},
        "permissions": {"tools": ["native:doc_search"], "scripts": [],
                        "network": "none",
                        "filesystem": {"read": [], "write": [""]},
                        "approval_required_for": []}})
    plat = Platform([str(tmp_path)], str(tmp_path / "data"))
    task = TaskSpec(task_id="perm", goal="do the test thing",
                    computations=[{"label": "x", "expression": "1 + 1"}],
                    skill_hint="no-calc")
    bundle = plat.run_task(task, record_episode=False)
    denied = [t for t in bundle["record"].traces
              if t.status == "permission_denied"]
    assert denied and denied[0].step_id.startswith("compute")


def test_script_not_in_allowlist_is_refused(tmp_path):
    _write_pkg(tmp_path, "script-skill", manifest_overrides={
        "governs": ["script"],
        "requires": {"tools": ["native:script_runner"], "capabilities": [],
                     "min_context_tokens": 0},
        "permissions": {"tools": ["native:script_runner"], "scripts": [],
                        "network": "none",
                        "filesystem": {"read": [], "write": [""]},
                        "approval_required_for": []}},
        extra_files={"scripts/run.py": "print('should never run')\n"})
    plat = Platform([str(tmp_path)], str(tmp_path / "data"))
    task = TaskSpec(task_id="scr", goal="run the script",
                    script_steps=[{"skill": "script-skill",
                                   "script": "scripts/run.py",
                                   "payload": {}, "label": "run"}],
                    skill_hint="script-skill")
    bundle = plat.run_task(task, record_episode=False)
    denied = [t for t in bundle["record"].traces
              if t.status == "permission_denied"]
    assert denied


def test_budget_governor_blocks_run(platform):
    bundle = platform.run_task(demo_task(), provider="stub-pro",
                               budget_tokens=100)
    assert bundle["record"].status == "budget_exceeded"


def test_provider_swap_same_plan_precision_differs(platform):
    pro = platform.run_task(demo_task(), provider="stub-pro",
                            record_episode=False)
    basic = platform.run_task(demo_task(), provider="stub-basic",
                              record_episode=False)
    assert pro["plan"].plan_hash() == basic["plan"].plan_hash()
    assert basic["record"].total_cost_usd < pro["record"].total_cost_usd
    # basic tier rounds decimal operands: its net revenue is the honest
    # wrong value, pro's is exact. This is the documented tier property.
    assert f"{TOTALS['net_revenue']:.2f}" in pro["record"].final_output
    assert f"{TOTALS['net_revenue']:.2f}" not in basic["record"].final_output


def test_replan_recovers_with_backup_agent(platform, tmp_path):
    providers = {"stub-pro": ScriptedProvider("stub-pro",
                                              flaky={"executor": 10}),
                 "stub-basic": ScriptedProvider("stub-basic")}
    runtime = ManagedRuntime(default_registry(), providers, platform.library,
                             CHUNKS, METRIC_ROWS, str(tmp_path / "sb"))
    bundle_plan = platform.planner.plan_task(
        demo_task(),
        platform.resolver.resolve(
            demo_task().goal,
            provider_capabilities=ScriptedProvider.CAPABILITIES["stub-pro"],
            pins=("data-analysis",)))
    record = runtime.run(bundle_plan)
    assert record.replans, "expected at least one replan"
    assert record.status == "completed"


# ---------------------------------------------------------------- episodes/audit

def test_episode_recorded_with_unlabelled_outcome(platform):
    platform.run_task(demo_task(), provider="stub-pro")
    eps = platform.episodes.all()
    assert eps, "expected an episode to be recorded"
    assert "data-analysis" in eps[-1]["skills_used"]
    assert eps[-1]["outcome"]["success"] is None  # never assumed
    labelled = platform.run_task(
        demo_task(), provider="stub-pro",
        verifier=lambda task, record: (record.status == "completed", "status"))
    assert labelled["episode"]["outcome"]["success"] is True
    assert platform.episodes.shapes()


def test_audit_chain_detects_tampering(platform):
    platform.audit.append("created", {"skill": "x"})
    platform.audit.append("lifecycle", {"skill": "x", "to": "active"})
    assert platform.audit.verify_chain()
    with open(platform.audit.path, "a") as fh:
        fh.write('{"seq": 99, "event": "forged", "payload": {}, '
                 '"prev": "x", "hash": "y", "ts": 0}\n')
    assert not platform.audit.verify_chain()
