"""Dynamic skill creation (Phase 1): the full flow, exercised
end-to-end with the offline provider — draft, static validation,
sandboxed trial, human gate, registration in shadow, promotion, and
the created skill governing a real run. Plus the refusal paths.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillforge import Platform, TaskSpec
from skillforge.corpus import TOTALS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_ROOT = os.path.join(ROOT, "library")


def _demonstration():
    rev = f"{TOTALS['revenue_all'] / TOTALS['units_all']:.2f}"
    cpu = f"{TOTALS['costs_all'] / TOTALS['units_all']:.2f}"
    return {
        "name": "unit-economics-snapshot",
        "task": "Give me the unit-economics snapshot for Q1",
        "steps": [
            "Look up total revenue, total costs and units sold.",
            "Compute revenue per unit and cost per unit.",
            "Write the snapshot: totals first, then per-unit figures."],
        "sections": ["Totals", "Per-unit figures", "Notes"],
        "lookups": [1], "computations": [1],
        "task_spec": {
            "goal": "Unit-economics snapshot for Q1 2026",
            "lookups": [
                {"label": "total revenue", "metric": "revenue_usd"},
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


@pytest.fixture()
def platform(tmp_path):
    lib_root = tmp_path / "library"
    lib_root.mkdir()
    return Platform([str(lib_root)], str(tmp_path / "data"))


def test_creation_end_to_end(platform):
    creator = platform.creator()
    result = creator.create(
        description="Compute a unit-economics snapshot for a quarter: "
                    "totals, then revenue per unit and cost per unit.",
        demonstration=_demonstration())
    assert result.ok, result.detail
    assert result.stage == "registered"
    assert result.lifecycle == "shadow"
    assert result.validation["valid"]
    assert result.trial["pass_rate"] == 1.0
    assert "unit-economics-snapshot" in platform.library.names()
    pkg = platform.library.get("unit-economics-snapshot")
    assert pkg.provenance.get("origin") == "dynamic-creation"
    assert pkg.provenance.get("trial", {}).get("pass_rate") == 1.0
    assert platform.audit.verify_chain()

    # Shadow: the resolver sees it, logs it, but it does not govern.
    task = TaskSpec(task_id="ue", goal="Give me the unit-economics snapshot "
                                       "for Q1",
                    lookups=_demonstration()["task_spec"]["lookups"],
                    computations=_demonstration()["task_spec"]["computations"],
                    title="Unit-economics snapshot Q1")
    shadow_run = platform.run_task(task, record_episode=False)
    assert shadow_run["resolution"].primary != "unit-economics-snapshot"
    assert "unit-economics-snapshot" in [
        s.name for s in shadow_run["resolution"].shadow_hits]

    # Promotion is a separate, audited act; afterwards it governs.
    platform.library.set_lifecycle("unit-economics-snapshot", "active",
                                   actor="tester")
    active_run = platform.run_task(task, record_episode=False)
    assert active_run["resolution"].primary == "unit-economics-snapshot"
    assert active_run["record"].status == "completed"
    assert f"{TOTALS['revenue_all']:.2f}" in active_run["record"].final_output


def test_creation_denied_at_gate_registers_nothing(platform):
    result = platform.creator().create(
        description="Compute a unit-economics snapshot for a quarter.",
        demonstration=_demonstration(),
        approver=lambda summary: False)
    assert not result.ok
    assert result.stage == "approval"
    assert "unit-economics-snapshot" not in platform.library.names()


def test_creation_rejects_invalid_spec(platform):
    spec = {
        "description": "A broken skill.",
        "body": "# broken\n\n## Purpose\n\nA broken skill.\n",
        "manifest": {"apiVersion": "skillforge/v1", "name": "broken-skill",
                     "version": "not-semver", "lifecycle": "whenever",
                     "triggers": {"examples": [], "counter_examples": []}},
        "cases": [],
    }
    result = platform.creator().create(spec=spec)
    assert not result.ok
    assert result.stage == "validation"
    assert "broken-skill" not in platform.library.names()
