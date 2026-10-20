"""The skill library: discovery, lifecycle, import and export.

The library is just a set of directories (roots scanned in order).
All lifecycle changes go through here so they are validated,
provenance-stamped and written to the audit chain — a lifecycle field
edited by hand is exactly the failure mode the platform exists to
prevent, so ``set_lifecycle`` re-validates the package before and
after the change.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile

import yaml

from .audit import AuditLog
from .packages import LIFECYCLES, SkillPackage, load_package
from .validate_pkg import ValidationReport, validate_package

EXPORT_NOTE = """# Portable export

This package was exported in *portable* mode: the `skill.yaml`
manifest and `provenance.json` were stripped, leaving the vanilla
Agent Skills folder (SKILL.md + files). What does not travel with it:

- enforced permissions (scripts/network/filesystem allowlists),
- trigger counter-examples and the eval suite's pass bar,
- capability requirements, budgets, and lifecycle state,
- provenance (who authored it, from what, verified how).

On a host that supports only the base format, this skill behaves the
way the base format always behaves: instructions are followed as well
as the host follows instructions, and nothing is enforced. Re-import
it into SkillForge to restore the guarantees.
"""


class LibraryError(Exception):
    pass


def permission_diff(pkg: SkillPackage) -> dict:
    """Plain-language summary of what a package asks for — the thing a
    human approves at import, before the package can leave shadow."""
    m = pkg.manifest
    lines = []
    tools = m.granted_tool_refs
    lines.append(f"Tools: {', '.join(tools) if tools else 'none'}")
    lines.append(f"Scripts it may run: "
                 f"{', '.join(m.perm_scripts) if m.perm_scripts else 'none'}")
    lines.append(f"Network: {m.perm_network}")
    lines.append(f"Files it may write: "
                 f"{', '.join(m.perm_fs_write) if m.perm_fs_write else 'sandbox only'}")
    lines.append(f"Needs human approval for: "
                 f"{', '.join(m.approval_required_for) if m.approval_required_for else 'nothing'}")
    return {"summary_lines": lines, "tools": tools,
            "scripts": m.perm_scripts, "network": m.perm_network,
            "fs_write": m.perm_fs_write,
            "approval_required_for": m.approval_required_for}


class Library:
    def __init__(self, roots: list[str], audit: AuditLog | None = None):
        self.roots = [os.path.abspath(r) for r in roots]
        self.audit = audit
        self._packages: dict[str, SkillPackage] = {}
        self.load_errors: list[str] = []
        self.reload()

    # -- discovery ------------------------------------------------------------
    def reload(self) -> None:
        self._packages = {}
        self.load_errors = []
        for root in self.roots:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root)):
                pdir = os.path.join(root, entry)
                if not os.path.isdir(pdir):
                    continue
                if not os.path.exists(os.path.join(pdir, "SKILL.md")):
                    continue
                try:
                    pkg = load_package(pdir)
                except Exception as exc:               # unreadable package
                    self.load_errors.append(f"{pdir}: {exc}")
                    continue
                if pkg.name in self._packages:
                    self.load_errors.append(
                        f"duplicate skill name {pkg.name!r} at {pdir} "
                        f"(first seen at {self._packages[pkg.name].path})")
                    continue
                self._packages[pkg.name] = pkg

    # -- access -----------------------------------------------------------------
    def get(self, name: str) -> SkillPackage:
        if name not in self._packages:
            raise LibraryError(f"unknown skill: {name}")
        return self._packages[name]

    def names(self, lifecycle: str | None = None) -> list[str]:
        return sorted(n for n, p in self._packages.items()
                      if lifecycle is None or p.lifecycle == lifecycle)

    def all(self) -> list[SkillPackage]:
        return [self._packages[n] for n in self.names()]

    def __len__(self):
        return len(self._packages)

    def validate_all(self) -> dict[str, ValidationReport]:
        return {p.name: validate_package(p.path) for p in self.all()}

    # -- lifecycle ---------------------------------------------------------------
    def set_lifecycle(self, name: str, state: str, actor: str = "user") -> SkillPackage:
        if state not in LIFECYCLES:
            raise LibraryError(f"unknown lifecycle state: {state}")
        pkg = self.get(name)
        before = validate_package(pkg.path)
        if not before.valid:
            raise LibraryError(f"{name} does not validate; refusing "
                               f"lifecycle change: {before.errors}")
        manifest_path = os.path.join(pkg.path, "skill.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            raw["lifecycle"] = state
            with open(manifest_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(raw, fh, sort_keys=False)
        else:
            raw = pkg.manifest.to_dict()
            raw["lifecycle"] = state
            with open(manifest_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(raw, fh, sort_keys=False)
        self._stamp_provenance(pkg.path, {"lifecycle_event":
                                          {"from": pkg.lifecycle, "to": state,
                                           "actor": actor, "at": time.time()}})
        if self.audit:
            self.audit.append("lifecycle", {"skill": name, "to": state,
                                            "actor": actor})
        self.reload()
        return self.get(name)

    def _stamp_provenance(self, pkg_dir: str, extra: dict) -> None:
        path = os.path.join(pkg_dir, "provenance.json")
        data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                data = {}
        data.update(extra)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)

    # -- import / export ------------------------------------------------------------
    def import_package(self, source: str, actor: str = "user") -> dict:
        """Import a package folder or .zip into the first library root.

        The package is validated first; an invalid package is refused.
        Imports land in the ``imported`` lifecycle state (vanilla) or
        ``shadow`` (native) — never directly active (design 3.1/3.3).
        """
        workdir = None
        if source.endswith(".zip"):
            import tempfile
            workdir = tempfile.mkdtemp(prefix="skillforge-import-")
            with zipfile.ZipFile(source) as zf:
                zf.extractall(workdir)
            candidates = [os.path.join(workdir, d) for d in os.listdir(workdir)
                          if os.path.isdir(os.path.join(workdir, d))]
            if len(candidates) != 1:
                raise LibraryError("zip must contain exactly one package folder")
            source = candidates[0]
        report = validate_package(source)
        if not report.valid:
            raise LibraryError(f"import refused, package invalid: {report.errors}")
        pkg = load_package(source)
        dest = os.path.join(self.roots[0], pkg.name)
        if os.path.exists(dest):
            raise LibraryError(f"skill {pkg.name!r} already in library")
        shutil.copytree(source, dest)
        target_state = "shadow" if pkg.manifest.native else "imported"
        loaded = load_package(dest)
        if loaded.lifecycle not in ("imported", "shadow"):
            self.set_lifecycle(pkg.name, target_state, actor=actor)
        diff = permission_diff(loaded)
        self._stamp_provenance(dest, {"origin": "import", "actor": actor,
                                      "imported_at": time.time(),
                                      "permission_summary": diff["summary_lines"]})
        if self.audit:
            self.audit.append("import", {"skill": pkg.name, "actor": actor,
                                         "lifecycle": target_state})
        self.reload()
        return {"skill": pkg.name, "lifecycle": target_state,
                "validation": report.to_dict(), "permission_diff": diff}

    def export_package(self, name: str, dest_path: str,
                        portable: bool = False) -> str:
        pkg = self.get(name)
        tmp = dest_path + ".tmpdir"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        shutil.copytree(pkg.path, tmp)
        if portable:
            for rel in ("skill.yaml", "provenance.json"):
                p = os.path.join(tmp, rel)
                if os.path.exists(p):
                    os.remove(p)
            with open(os.path.join(tmp, "EXPORT_NOTE.md"), "w",
                      encoding="utf-8") as fh:
                fh.write(EXPORT_NOTE)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(tmp):
                for f in files:
                    full = os.path.join(root, f)
                    # The zip holds ONE package folder at its root —
                      # the same shape import_package accepts.
                    zf.write(full, os.path.join(
                        name, os.path.relpath(full, tmp)))
        shutil.rmtree(tmp)
        return dest_path


def write_provenance(pkg_dir: str, data: dict) -> str:
    path = os.path.join(pkg_dir, "provenance.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    return path
