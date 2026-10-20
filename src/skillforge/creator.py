"""Dynamic skill creation (design Part 3.3), end to end.

The flow, with no step skippable:

    describe (or demonstrate) -> DRAFT -> static validation ->
    sandboxed trial against the draft's own evals -> HUMAN APPROVAL
    GATE -> register as shadow (promotion to active is a separate,
    separately-approved step)

Two drafting paths implement one interface:

- ``draft_from_spec`` — the caller supplies the package contents
  explicitly (used by tests and by API clients).
- ``draft_from_description`` — the offline drafter: a deterministic
  drafting agent that composes the package from a capability
  description plus an optional demonstration (a task the user
  performed once, with its input and output). With a real model behind
  the seam this is where an LLM would draft; the deterministic drafter
  exists so the *whole flow* — gate included — is exercisable and
  testable with no keys. What it produces is deliberately plain: a
  correct skeleton with the demonstrated procedure, least-privilege
  permissions, and starter evals derived from the demonstration (one
  positive trigger, one near-miss counter-example, one task case whose
  expectations come from the demonstration's own output — the
  candidate proposes the exam's *questions from evidence*, and the
  trial still runs them against platform fixtures).

Provenance is written at registration: author, origin, the source
description's hash, and the trial scores. A skill without provenance
did not happen (guardrail 5).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time

import yaml

from .library import Library, permission_diff, write_provenance
from .packages import Manifest, load_package
from .validate_pkg import validate_package

_KEBAB = re.compile(r"[^a-z0-9]+")


def kebab(text: str) -> str:
    return _KEBAB.sub("-", text.lower()).strip("-")[:48].strip("-")


GENERIC_COUNTER = "Summarise this paragraph in one sentence and tell me " \
                  "what it is about."


class CreationResult:
    def __init__(self):
        self.ok = False
        self.stage = "draft"          # draft|validation|trial|approval|registered
        self.name: str | None = None
        self.draft_dir: str | None = None
        self.validation: dict | None = None
        self.trial: dict | None = None
        self.permission_summary: list = []
        self.lifecycle: str | None = None
        self.detail: str = ""

    def to_dict(self) -> dict:
        return vars(self).copy()


class SkillCreator:
    def __init__(self, platform):
        self.platform = platform

    # ------------------------------------------------------------------
    # Drafting
    # ------------------------------------------------------------------
    def draft_from_description(self, description: str,
                               demonstration: dict | None = None,
                               name: str | None = None,
                               author: str = "user") -> str:
        """Write a draft package to a temp dir; return its path."""
        demonstration = demonstration or {}
        name = name or kebab(self._name_seed(description, demonstration))
        demo_task = demonstration.get("task", description)
        demo_output = demonstration.get("output", "")
        steps = demonstration.get("steps") or [
            "Confirm the inputs the task needs are present.",
            "Gather the source figures or text the capability works on.",
            "Compute or compose the result, showing the working.",
            "Check the result against the source figures before writing.",
        ]
        sections = demonstration.get("sections") or ["Summary", "Working",
                                                     "Result"]
        tools = ["native:doc_search"]
        governs = ["research", "synthesize", "write"]
        if demonstration.get("lookups"):
            tools.append("native:data_lookup")
            governs.insert(1, "lookup")
        if demonstration.get("computations"):
            tools.append("native:calculator")
            governs.insert(2, "compute")
        tools.append("native:file_writer")

        body_lines = [
            f"# {name}", "",
            "## Purpose", "", description.strip(), "",
            "## When to use", "",
            f"Use this skill when the task is: {demo_task}", "",
            "## Procedure", "",
        ]
        body_lines += [f"{i + 1}. {s}" for i, s in enumerate(steps)]
        body_lines += ["", "## Output", "",
                       "Write the deliverable with these sections: "
                       + ", ".join(sections) + ".", ""]
        body = "\n".join(body_lines)

        manifest = Manifest(
            name=name, version="0.1.0", lifecycle="draft",
            api_version="skillforge/v1",
            trigger_examples=[demo_task],
            trigger_counter_examples=[GENERIC_COUNTER],
            requires_tools=tools, perm_tools=tools,
            perm_network="none", perm_fs_write=[""],
            governs=governs,
            output_sections=list(sections),
            evals_min_pass=0.9)
        cases = [
            {"id": "t1", "kind": "trigger", "task": demo_task,
             "should_fire": True},
            {"id": "t2", "kind": "trigger", "task": GENERIC_COUNTER,
             "should_fire": False},
        ]
        if demonstration.get("task_spec") and demonstration.get("expect"):
            cases.append({"id": "k1", "kind": "task",
                          "task": demonstration["task_spec"],
                          "expect": demonstration["expect"]})
        return self._write_draft(name, body, manifest, cases, author,
                                 origin="dynamic-creation",
                                 source=description)

    def draft_from_spec(self, spec: dict, author: str = "user") -> str:
        """Write a draft package from an explicit spec mapping."""
        manifest = Manifest.from_dict(spec["manifest"])
        cases = spec.get("cases", [])
        return self._write_draft(manifest.name, spec["body"], manifest,
                                 cases, author, origin=spec.get("origin", "spec"),
                                 source=str(spec.get("source", "")),
                                 extra_files=spec.get("files", {}),
                                 description=spec.get("description"))

    def _name_seed(self, description: str, demonstration: dict) -> str:
        if demonstration.get("name"):
            return demonstration["name"]
        words = [w for w in re.findall(r"[a-z]+", description.lower())
                 if len(w) > 2][:4]
        return "-".join(words) or "new-skill"

    def _write_draft(self, name, body, manifest: Manifest, cases,
                     author, origin, source, extra_files=None,
                     description=None) -> str:
        draft_dir = tempfile.mkdtemp(prefix=f"skillforge-draft-{name}-")
        pkg_dir = os.path.join(draft_dir, name)
        os.makedirs(os.path.join(pkg_dir, "evals"))
        frontmatter = {"name": name,
                       "description": description or self._description_of(body)}
        with open(os.path.join(pkg_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\n")
            yaml.safe_dump(frontmatter, fh, sort_keys=False)
            fh.write("---\n\n")
            fh.write(body if body.endswith("\n") else body + "\n")
        with open(os.path.join(pkg_dir, "skill.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(manifest.to_dict(), fh, sort_keys=False)
        with open(os.path.join(pkg_dir, "evals", "cases.yaml"), "w",
                  encoding="utf-8") as fh:
            yaml.safe_dump({"cases": cases}, fh, sort_keys=False)
        for rel, content in (extra_files or {}).items():
            target = os.path.join(pkg_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
        write_provenance(pkg_dir, {
            "author": author, "origin": origin,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest()[:16],
            "drafted_at": time.time(), "state": "draft"})
        return pkg_dir

    @staticmethod
    def _description_of(body: str) -> str:
        # The description is the trigger; the drafter takes it from the
        # Purpose paragraph's first sentence.
        m = re.search(r"## Purpose\s+(.+?)(?:\n\n|\Z)", body, re.S)
        if m:
            text = " ".join(m.group(1).split())
            return text[:300]
        return "A dynamically created skill."

    # ------------------------------------------------------------------
    # The full flow
    # ------------------------------------------------------------------
    def create(self, description: str | None = None,
               demonstration: dict | None = None,
               spec: dict | None = None,
               approver=None, actor: str = "user",
               target_lifecycle: str = "shadow") -> CreationResult:
        """Run draft -> validate -> trial -> gate -> register.

        ``approver`` receives the plain-language permission summary
        plus validation and trial results, and returns True/False.
        Default approver approves (demo convenience); the server never
        uses the default — its gate is a human mutation.
        """
        approver = approver or (lambda summary: True)
        result = CreationResult()
        if spec is not None:
            draft_dir = self.draft_from_spec(spec, author=actor)
        else:
            draft_dir = self.draft_from_description(
                description or "", demonstration, author=actor)
        result.draft_dir = draft_dir
        pkg = load_package(draft_dir)
        result.name = pkg.name

        report = validate_package(draft_dir)
        result.validation = report.to_dict()
        if not report.valid:
            result.stage = "validation"
            result.detail = f"static validation failed: {report.errors}"
            return result

        # Sandboxed trial: evaluate the draft inside an isolated
        # library rooted at the draft's parent, so the candidate is
        # scored exactly as the platform scores any package.
        trial_platform = self.platform.ephemeral(library_roots=[os.path.dirname(draft_dir)])
        from .evals import EvalRunner
        trial_pkg = trial_platform.library.get(pkg.name)
        trial = EvalRunner(trial_platform).run_package(trial_pkg)
        result.trial = trial.to_dict()
        result.stage = "trial"
        if trial.pass_rate < pkg.manifest.evals_min_pass:
            result.detail = (f"trial pass rate {trial.pass_rate:.2f} below "
                             f"the package's bar {pkg.manifest.evals_min_pass}")
            return result

        summary = {"skill": pkg.name,
                   "permissions": permission_diff(pkg)["summary_lines"],
                   "validation": result.validation,
                   "trial": result.trial}
        result.permission_summary = summary["permissions"]
        if not approver(summary):
            result.stage = "approval"
            result.detail = "human approver denied registration"
            if self.platform.audit:
                self.platform.audit.append("creation_denied",
                                           {"skill": pkg.name, "actor": actor})
            return result

        # Register: copy into the library root, stamp provenance, set
        # lifecycle (shadow by default; promotion is a separate act).
        dest = os.path.join(self.platform.library.roots[0], pkg.name)
        if os.path.exists(dest):
            result.detail = f"a skill named {pkg.name} already exists"
            return result
        shutil.copytree(draft_dir, dest)
        write_provenance(dest, {
            "author": actor, "origin": "dynamic-creation",
            "created_at": time.time(),
            "trial": {"pass_rate": trial.pass_rate, "passed": trial.passed,
                      "total": trial.total},
            "approved_by": actor})
        self.platform.library.reload()
        if self.platform.library.get(pkg.name).lifecycle != target_lifecycle:
            self.platform.library.set_lifecycle(pkg.name, target_lifecycle,
                                                actor=actor)
        if self.platform.audit:
            self.platform.audit.append("created", {"skill": pkg.name,
                                                   "actor": actor,
                                                   "lifecycle": target_lifecycle,
                                                   "trial_pass_rate": trial.pass_rate})
        result.ok = True
        result.stage = "registered"
        result.lifecycle = target_lifecycle
        result.detail = (f"registered as {target_lifecycle}; trial "
                          f"{trial.passed}/{trial.total} passed")
        return result
