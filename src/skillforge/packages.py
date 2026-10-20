"""Skill packages: the portable unit of procedural knowledge.

A package is a folder (design Part 3.1):

    name/
    |-- SKILL.md          Agent Skills standard: YAML frontmatter
    |                     (name, description) + instruction body.
    |-- skill.yaml        SkillForge manifest: triggers, requirements,
    |                     permissions, composition, budget, evals.
    |-- scripts/          optional executables (allowlisted, sandboxed)
    |-- references/       optional on-demand docs (progressive disclosure)
    |-- assets/           optional templates/data
    |-- evals/            trigger cases + task cases (+ verifiers.py)
    `-- provenance.json   written by the platform, never by hand

A folder with only SKILL.md is a *vanilla* Agent Skill: it loads with a
synthesised manifest carrying safe defaults (no scripts, no network,
lifecycle ``imported``) — import compatibility with the existing
ecosystem is a design requirement, not a favour.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field

import yaml

LIFECYCLES = ("draft", "shadow", "active", "deprecated", "imported")
KNOWN_CAPABILITIES = ("tool_calling", "long_context", "vision", "code_execution")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

@dataclass
class Manifest:
    name: str
    version: str = "0.1.0"
    lifecycle: str = "draft"
    api_version: str = "skillforge/v1"
    trigger_examples: list = field(default_factory=list)
    trigger_counter_examples: list = field(default_factory=list)
    requires_tools: list = field(default_factory=list)
    requires_capabilities: list = field(default_factory=list)
    min_context_tokens: int = 0
    perm_tools: list = field(default_factory=list)
    perm_scripts: list = field(default_factory=list)
    perm_network: str = "none"                 # none | allowlist | any
    perm_fs_read: list = field(default_factory=list)
    perm_fs_write: list = field(default_factory=list)
    approval_required_for: list = field(default_factory=list)
    composes: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    governs: list = field(default_factory=list)   # actions this skill governs
    output_sections: list = field(default_factory=list)
    budget_tokens_per_run: int | None = None
    budget_script_seconds: int | None = None
    evals_suite: str = "evals/cases.yaml"
    evals_holdout: str | None = None
    evals_min_pass: float = 0.9
    native: bool = True                          # False for vanilla imports

    @property
    def granted_tool_refs(self) -> list:
        """Tool allowlist = requires.tools ∪ permissions.tools."""
        out = list(self.requires_tools)
        for t in self.perm_tools:
            if t not in out:
                out.append(t)
        return out

    def granted_local_tools(self) -> set:
        """Local tool names this package grants (native: refs only)."""
        names = set()
        for ref in self.granted_tool_refs:
            local = tool_local_name(ref)
            if local:
                names.add(local)
        return names

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        trig = d.get("triggers") or {}
        req = d.get("requires") or {}
        perm = d.get("permissions") or {}
        fs = perm.get("filesystem") or {}
        comp = d.get("composition") or {}
        budget = d.get("budget") or {}
        ev = d.get("evals") or {}
        out = d.get("output") or {}
        return cls(
            name=d.get("name", ""),
            version=str(d.get("version", "0.1.0")),
            lifecycle=d.get("lifecycle", "draft"),
            api_version=d.get("apiVersion", ""),
            trigger_examples=list(trig.get("examples") or []),
            trigger_counter_examples=list(trig.get("counter_examples") or []),
            requires_tools=list(req.get("tools") or []),
            requires_capabilities=list(req.get("capabilities") or []),
            min_context_tokens=int(req.get("min_context_tokens") or 0),
            perm_tools=list(perm.get("tools") or []),
            perm_scripts=list(perm.get("scripts") or []),
            perm_network=perm.get("network", "none"),
            perm_fs_read=list(fs.get("read") or []),
            perm_fs_write=list(fs.get("write") or []),
            approval_required_for=list(perm.get("approval_required_for") or []),
            composes=list(comp.get("composes") or []),
            conflicts=list(comp.get("conflicts") or []),
            governs=list(d.get("governs") or []),
            output_sections=list(out.get("sections") or []),
            budget_tokens_per_run=budget.get("max_tokens_per_run"),
            budget_script_seconds=budget.get("max_script_seconds"),
            evals_suite=ev.get("suite", "evals/cases.yaml"),
            evals_holdout=ev.get("holdout"),
            evals_min_pass=float(ev.get("min_pass", 0.9)),
        )

    @classmethod
    def vanilla(cls, name: str) -> "Manifest":
        """Safe defaults synthesised for a manifest-less Agent Skill."""
        m = cls(name=name, lifecycle="imported", api_version="")
        m.native = False
        return m

    def to_dict(self) -> dict:
        return {
            "apiVersion": self.api_version or "skillforge/v1",
            "name": self.name, "version": self.version,
            "lifecycle": self.lifecycle,
            "triggers": {"examples": self.trigger_examples,
                         "counter_examples": self.trigger_counter_examples},
            "requires": {"tools": self.requires_tools,
                         "capabilities": self.requires_capabilities,
                         "min_context_tokens": self.min_context_tokens},
            "permissions": {"tools": self.perm_tools,
                            "scripts": self.perm_scripts,
                            "network": self.perm_network,
                            "filesystem": {"read": self.perm_fs_read,
                                           "write": self.perm_fs_write},
                            "approval_required_for": self.approval_required_for},
            "composition": {"composes": self.composes,
                            "conflicts": self.conflicts},
            "governs": self.governs,
            "output": {"sections": self.output_sections},
            "budget": {"max_tokens_per_run": self.budget_tokens_per_run,
                       "max_script_seconds": self.budget_script_seconds},
            "evals": {"suite": self.evals_suite, "holdout": self.evals_holdout,
                      "min_pass": self.evals_min_pass},
        }


def tool_local_name(ref: str) -> str | None:
    """Map a manifest tool ref to a local tool name, if it has one.

    ``native:calculator`` -> ``calculator``. ``mcp:<server>/<tool>``
    refs name external plugin-layer tools: declared, governed, but
    not executable by the local runtime (returns None).
    """
    if ref.startswith("native:"):
        return ref.split(":", 1)[1]
    return None


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------

class PackageError(Exception):
    """A package folder could not be parsed at all."""


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise PackageError(f"unparseable SKILL.md frontmatter: {exc}") from exc
    if not isinstance(fm, dict):
        raise PackageError("SKILL.md frontmatter is not a mapping")
    return fm, body


@dataclass
class SkillPackage:
    path: str                       # package directory
    name: str
    description: str
    body: str                       # SKILL.md instruction body (L2 content)
    frontmatter: dict
    manifest: Manifest
    provenance: dict = field(default_factory=dict)

    @property
    def has_manifest(self) -> bool:
        return os.path.exists(os.path.join(self.path, "skill.yaml"))

    @property
    def lifecycle(self) -> str:
        return self.manifest.lifecycle

    def content_hash(self) -> str:
        h = hashlib.sha256()
        for rel in ("SKILL.md", "skill.yaml"):
            p = os.path.join(self.path, rel)
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    h.update(fh.read())
        return h.hexdigest()[:16]

    def scripts_on_disk(self) -> list:
        sdir = os.path.join(self.path, "scripts")
        if not os.path.isdir(sdir):
            return []
        return sorted(f"scripts/{f}" for f in os.listdir(sdir)
                      if os.path.isfile(os.path.join(sdir, f)))

    def summary(self) -> dict:
        """Plain-language permission + identity summary (for gates/UI)."""
        m = self.manifest
        return {
            "name": self.name, "version": m.version, "lifecycle": m.lifecycle,
            "description": self.description,
            "tools": m.granted_tool_refs,
            "scripts": m.perm_scripts, "network": m.perm_network,
            "fs_write": m.perm_fs_write,
            "approval_required_for": m.approval_required_for,
            "composes": m.composes, "conflicts": m.conflicts,
            "author": (self.provenance or {}).get("author", "unknown"),
            "origin": (self.provenance or {}).get("origin", "unknown"),
        }


def load_package(path: str) -> SkillPackage:
    """Parse a package folder. Raises PackageError on unreadable core."""
    skill_md = os.path.join(path, "SKILL.md")
    if not os.path.exists(skill_md):
        raise PackageError(f"{path}: SKILL.md missing")
    with open(skill_md, encoding="utf-8") as fh:
        text = fh.read()
    frontmatter, body = _split_frontmatter(text)
    name = str(frontmatter.get("name") or os.path.basename(os.path.abspath(path)))
    description = str(frontmatter.get("description") or "")
    manifest_path = os.path.join(path, "skill.yaml")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            try:
                raw = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise PackageError(f"{path}: unparseable skill.yaml: {exc}") from exc
        if not isinstance(raw, dict):
            raise PackageError(f"{path}: skill.yaml is not a mapping")
        manifest = Manifest.from_dict(raw)
        if not manifest.name:
            manifest.name = name
    else:
        manifest = Manifest.vanilla(name)
    provenance = {}
    prov_path = os.path.join(path, "provenance.json")
    if os.path.exists(prov_path):
        try:
            with open(prov_path, encoding="utf-8") as fh:
                provenance = json.load(fh)
        except (json.JSONDecodeError, OSError):
            provenance = {"_corrupt": True}
    return SkillPackage(path=os.path.abspath(path), name=name,
                        description=description, body=body,
                        frontmatter=frontmatter, manifest=manifest,
                        provenance=provenance)
