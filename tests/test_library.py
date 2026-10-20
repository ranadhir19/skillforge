"""Behavioural suites: every starter skill's own eval cases, executed
by the platform (trigger regression against the whole library +
end-to-end task cases against the seeded fixtures).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillforge import Platform

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_ROOT = os.path.join(ROOT, "library")


@pytest.fixture(scope="module")
def platform(tmp_path_factory):
    return Platform([LIB_ROOT], str(tmp_path_factory.mktemp("data")))


def test_full_library_evals_on_pro(platform):
    """The starter library's contract: every skill passes its whole
    suite (trigger + task) on the pro offline tier."""
    evaluator = platform.evaluator()
    failures = []
    total = passed = 0
    for pkg in platform.library.all():
        rep = evaluator.run_package(pkg, provider="stub-pro")
        total += rep.total
        passed += rep.passed
        for r in rep.results:
            if not r.passed:
                failures.append(f"{pkg.name}/{r.case_id}: {r.detail}")
    assert total == 100, f"expected 100 cases across 20 skills, got {total}"
    assert passed == total, "eval failures:\n" + "\n".join(failures)


def test_trigger_precision_and_recall(platform):
    """Aggregate trigger quality over all 80 trigger cases (40 should
    fire, 40 near-miss counter-examples should not)."""
    evaluator = platform.evaluator()
    tp = fp = fn = tn = 0
    for pkg in platform.library.all():
        rep = evaluator.run_package(pkg, provider="stub-pro", kinds=("trigger",))
        from skillforge.evals import load_cases
        expected = {c["id"]: bool(c["should_fire"])
                    for c in load_cases(pkg) if c["kind"] == "trigger"}
        for r in rep.results:
            want = expected[r.case_id]
            if want and r.passed:
                tp += 1
            elif want and not r.passed:
                fn += 1
            elif not want and r.passed:
                tn += 1
            else:
                fp += 1
    assert (tp, fp, fn, tn) == (40, 0, 0, 40)


def test_basic_tier_precision_gap_is_in_the_numbers(platform):
    """Documented tier property: the basic scripted tier rounds decimal
    operands, so exact-figure task cases fail there while passing on
    pro. Both directions asserted — the gap is measured, not hidden."""
    evaluator = platform.evaluator()
    for name in ("verification-before-completion", "data-analysis"):
        pkg = platform.library.get(name)
        pro = evaluator.run_package(pkg, provider="stub-pro", kinds=("task",))
        basic = evaluator.run_package(pkg, provider="stub-basic", kinds=("task",))
        assert pro.pass_rate == 1.0, f"{name} should pass fully on stub-pro"
        assert basic.pass_rate < 1.0, f"{name} should show the rounding gap on stub-basic"
