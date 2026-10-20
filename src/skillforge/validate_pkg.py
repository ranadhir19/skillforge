"""Static validation for skill packages.

The design-registry discipline from governed-agents applied to skill
packages: a package that is incomplete or internally inconsistent is
*refused loudly*, never silently repaired. Validation is purely
static — it parses the folder and checks the contract (frontmatter,
manifest sync, referenced files, permission coverage of every script,
eval-suite shape). Behaviour is the eval runner's job (evals.py).

Errors fail validation. Warnings (over-long bodies, missing
counter-examples on imported packages, …) are reported but do not.
"""

from __future__ import annotations

import os
import re

import yaml

from .packages import (KNOWN_CAPABILITIES, LIFECYCLES, NAME_RE,
                       PackageError, SkillPackage, load_package)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ValidationReport:
    def __init__(self, path: str):
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"path": self.path, "valid": self.valid,
                "errors": self.errors, "warnings": self.warnings}

    def __str__(self) -> str:
        lines = [f"{self.path}: {'VALID' if self.valid else 'INVALID'}"]
        lines += [f"  ERROR: {e}" for e in self.errors]
        lines += [f"  warn:  {w}" for w in self.warnings]
        return "\n".join(lines)


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def validate_package(path: str) -> ValidationReport:
    rep = ValidationReport(path)
    try:
        pkg = load_package(path)
    except PackageError as exc:
        rep.errors.append(str(exc))
        return rep
    _validate(pkg, rep)
    return rep


def _validate(pkg: SkillPackage, rep: ValidationReport) -> None:
    m = pkg.manifest
    dirname = os.path.basename(pkg.path)

    # -- identity ------------------------------------------------------------
    if not NAME_RE.match(pkg.name):
        rep.errors.append(f"name {pkg.name!r} is not kebab-case")
    if pkg.name != dirname:
        rep.errors.append(
            f"name {pkg.name!r} does not match directory {dirname!r}")
    if m.native and m.name and m.name != pkg.name:
        rep.errors.append(
            f"skill.yaml name {m.name!r} != SKILL.md name {pkg.name!r}")
    if not pkg.description:
        rep.errors.append("SKILL.md frontmatter has no description "
                          "(the description is the trigger — it is required)")
    elif len(pkg.description) > 1024:
        rep.warnings.append("description exceeds 1024 chars (spec guidance)")

    # -- body size (progressive disclosure budget) ----------------------------
    if _est_tokens(pkg.body) > 5000:
        rep.warnings.append(
            f"SKILL.md body ~{_est_tokens(pkg.body)} tokens exceeds the "
            "5000-token progressive-disclosure guidance; move detail to "
            "references/")

    if not m.native:
        rep.warnings.append("vanilla package (no skill.yaml): synthesised "
                            "manifest with safe defaults; lifecycle=imported")
        return

    # -- manifest contract ------------------------------------------------------
    if m.api_version != "skillforge/v1":
        rep.errors.append(f"apiVersion {m.api_version!r} != 'skillforge/v1'")
    if not SEMVER_RE.match(m.version):
        rep.errors.append(f"version {m.version!r} is not semver (x.y.z)")
    if m.lifecycle not in LIFECYCLES:
        rep.errors.append(f"lifecycle {m.lifecycle!r} not in {LIFECYCLES}")
    if not m.trigger_examples:
        rep.errors.append("triggers.examples is empty — a native package "
                          "must declare example tasks that should fire it")
    if not m.trigger_counter_examples:
        rep.warnings.append("triggers.counter_examples is empty — "
                            "near-misses are what make trigger precision "
                            "testable; add at least one")
    for cap in m.requires_capabilities:
        if cap not in KNOWN_CAPABILITIES:
            rep.errors.append(f"unknown required capability {cap!r}")
    if m.perm_network not in ("none", "allowlist", "any"):
        rep.errors.append(f"permissions.network {m.perm_network!r} invalid")

    # -- scripts: declared <-> on disk, both directions -------------------------
    on_disk = set(pkg.scripts_on_disk())
    declared = set(m.perm_scripts)
    for s in sorted(declared - on_disk):
        rep.errors.append(f"permissions.scripts lists {s} but the file "
                          "does not exist")
    for s in sorted(on_disk - declared):
        rep.errors.append(f"{s} exists but is not in permissions.scripts "
                          "(unlisted scripts never run — declare it or "
                          "remove it)")

    # -- referenced files ---------------------------------------------------------
    for rel in (m.evals_suite, m.evals_holdout):
        if rel and not os.path.exists(os.path.join(pkg.path, rel)):
            rep.errors.append(f"evals file referenced but missing: {rel}")

    # -- eval suite shape -----------------------------------------------------------
    suite = os.path.join(pkg.path, m.evals_suite)
    if os.path.exists(suite):
        try:
            with open(suite, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            cases = data.get("cases")
            if not isinstance(cases, list) or not cases:
                rep.errors.append(f"{m.evals_suite}: 'cases' must be a "
                                  "non-empty list")
            else:
                for i, case in enumerate(cases):
                    _validate_case(pkg, case, i, rep)
        except yaml.YAMLError as exc:
            rep.errors.append(f"{m.evals_suite}: unparseable YAML: {exc}")

    # -- provenance ------------------------------------------------------------------
    if pkg.provenance.get("_corrupt"):
        rep.errors.append("provenance.json is corrupt (unparseable)")


def _validate_case(pkg: SkillPackage, case, i: int, rep: ValidationReport) -> None:
    where = f"{pkg.manifest.evals_suite} case #{i}"
    if not isinstance(case, dict):
        rep.errors.append(f"{where}: not a mapping")
        return
    cid = case.get("id")
    if not cid:
        rep.errors.append(f"{where}: missing 'id'")
    kind = case.get("kind")
    if kind not in ("trigger", "task"):
        rep.errors.append(f"{where} ({cid}): kind must be 'trigger' or 'task'")
        return
    if kind == "trigger":
        if "task" not in case or "should_fire" not in case:
            rep.errors.append(f"{where} ({cid}): trigger cases need 'task' "
                              "and 'should_fire'")
    else:
        spec = case.get("task")
        if not isinstance(spec, dict) or "goal" not in spec:
            rep.errors.append(f"{where} ({cid}): task cases need a task "
                              "mapping with a 'goal'")
        if "expect" not in case:
            rep.errors.append(f"{where} ({cid}): task cases need an 'expect' "
                              "block (deterministic assertions)")
