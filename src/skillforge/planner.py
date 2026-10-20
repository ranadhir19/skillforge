"""The planner: a task + a resolution becomes a skill-governed DAG.

Design Part 3.2: planning and triggering are separate. The resolver
decides *which skills are active*; the planner composes the workflow
and annotates each step with its governing skill — the skill whose
`governs` list covers the step's action, preferring the resolution's
primary skill. Steps no active skill governs run ungoverned (the
trace says so; ungoverned is a visible state, not a hidden default).

Sensitivity (human approval) is resolved at plan time from two
sources: the executor agent's ``approval_actions`` and the governing
skill's manifest ``approval_required_for`` — either one gates the
step.
"""

from __future__ import annotations

import re

from .corpus import TaskSpec
from .registry import AgentRegistry
from .resolver import Resolution
from .workflow import PlanStep, WorkflowPlan


class SkillPlanner:
    def __init__(self, registry: AgentRegistry, library):
        self.registry = registry
        self.library = library

    def _agent_for(self, action: str) -> str:
        cands = self.registry.with_action(action)
        if not cands:
            raise ValueError(f"no agent can perform action {action!r}")
        return cands[0].name

    def _governing(self, action: str, resolution: Resolution) -> str | None:
        """The active skill governing ``action``: primary first, then
        any other active skill whose manifest governs the action."""
        active = resolution.names()
        if resolution.primary and resolution.primary in active:
            pkg = self.library.get(resolution.primary)
            if action in pkg.manifest.governs:
                return resolution.primary
        for name in active:
            if action in self.library.get(name).manifest.governs:
                return name
        return None

    def _sensitive(self, step: PlanStep) -> bool:
        agent = self.registry.get(step.agent)
        if step.action in agent.approval_actions:
            return True
        if step.skill:
            pkg = self.library.get(step.skill)
            if step.action in pkg.manifest.approval_required_for:
                return True
        return False

    # -- structured tasks -------------------------------------------------------
    def plan_task(self, task: TaskSpec, resolution: Resolution) -> WorkflowPlan:
        steps: list[PlanStep] = []
        gather_ids: list[str] = []

        for i, q in enumerate(task.sub_questions):
            sid = f"research_{i + 1}"
            steps.append(PlanStep(
                sid, self._agent_for("research"), "research", q,
                skill=self._governing("research", resolution)))
            gather_ids.append(sid)

        lookup_ids = []
        for i, lk in enumerate(task.lookups):
            sid = f"lookup_{i + 1}"
            steps.append(PlanStep(
                sid, self._agent_for("lookup"), "lookup",
                f"Look up {lk.get('label', lk['metric'])}",
                skill=self._governing("lookup", resolution), params=dict(lk)))
            lookup_ids.append(sid)
            gather_ids.append(sid)

        label_to_id = {lk.get("label", lk["metric"]): f"lookup_{i + 1}"
                       for i, lk in enumerate(task.lookups)}
        compute_ids = []
        for i, comp in enumerate(task.computations):
            sid = f"compute_{i + 1}"
            params = dict(comp)
            if comp.get("refs"):
                params["_ref_labels"] = label_to_id
            steps.append(PlanStep(
                sid, self._agent_for("compute"), "compute",
                f"Compute {comp.get('label', 'value')}",
                skill=self._governing("compute", resolution),
                depends_on=tuple(lookup_ids), params=params))
            compute_ids.append(sid)
            gather_ids.append(sid)
            label_to_id[comp.get("label", sid)] = sid

        for i, ss in enumerate(task.script_steps):
            sid = f"script_{i + 1}"
            steps.append(PlanStep(
                sid, self._agent_for("script"), "script",
                f"Run {ss['script']} ({ss.get('label', '')})",
                skill=ss["skill"],
                params={"script": ss["script"],
                        "payload": ss.get("payload", {}),
                        "label": ss.get("label", ss["script"])}))
            gather_ids.append(sid)

        sections: tuple = ()
        if resolution.primary:
            sections = tuple(self.library.get(resolution.primary)
                             .manifest.output_sections)
        deps = tuple(gather_ids)
        steps.append(PlanStep(
            "synthesize", self._agent_for("synthesize"), "synthesize",
            f"Synthesize findings for: {task.goal}",
            skill=self._governing("synthesize", resolution), depends_on=deps))
        steps.append(PlanStep(
            "write", self._agent_for("write"), "write",
            f"Write the deliverable: {task.title}",
            skill=resolution.primary, depends_on=("synthesize",),
            params={"title": task.title, "output_sections": list(sections)}))
        if task.publish_to:
            steps.append(PlanStep(
                "publish", self._agent_for("publish"), "publish",
                f"Publish the deliverable to {task.publish_to}",
                skill=resolution.primary, depends_on=("write",),
                params={"filename": task.publish_to}))
        plan = WorkflowPlan(task.task_id, task.goal, steps, origin="dynamic")
        for s in plan.steps:
            s.sensitive = self._sensitive(s)
        plan.validate()
        return plan

    # -- free-text tasks ------------------------------------------------------------
    def plan_text(self, task_text: str, resolution: Resolution,
                  task_id: str = "adhoc") -> WorkflowPlan:
        sections: tuple = ()
        if resolution.primary:
            sections = tuple(self.library.get(resolution.primary)
                             .manifest.output_sections)
        steps = [
            PlanStep("research_1", self._agent_for("research"), "research",
                     task_text,
                     skill=self._governing("research", resolution)),
            PlanStep("synthesize", self._agent_for("synthesize"), "synthesize",
                     f"Synthesize findings for: {task_text}",
                     skill=self._governing("synthesize", resolution),
                     depends_on=("research_1",)),
            PlanStep("write", self._agent_for("write"), "write",
                     "Write the deliverable",
                     skill=resolution.primary, depends_on=("synthesize",),
                     params={"title": "Deliverable",
                             "output_sections": list(sections)}),
        ]
        plan = WorkflowPlan(task_id, task_text, steps, origin="dynamic")
        for s in plan.steps:
            s.sensitive = self._sensitive(s)
        plan.validate()
        return plan


_EXPR_REF_RE = re.compile(r"\{([^{}]+)\}")


def resolve_expression(expression: str, results: dict, label_to_id: dict) -> str:
    """Substitute {label} references in a compute expression with the
    numeric results of earlier steps."""
    def sub(m):
        label = m.group(1)
        sid = label_to_id.get(label)
        if sid is None or sid not in results:
            raise KeyError(f"unresolved expression reference: {label}")
        return repr(float(results[sid]["value"]))
    return _EXPR_REF_RE.sub(sub, expression)
