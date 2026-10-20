"""The managed runtime: governed execution of skill-annotated plans.

Adapted from open-managed-agents' runtime (budget governor, approval
gates, retry + replan, full traces) with the SkillForge governance
layer from design Part 3.5 enforced *at the tool boundary*:

- every step runs under its governing skill's manifest: the tool allow
  list is the intersection of the agent's grant and the skill's grant;
  a step whose action needs a tool its skill does not grant is refused
  with status ``permission_denied`` — never silently re-routed;
- filesystem writes must fall inside the skill's declared write
  scopes (relative to the run sandbox);
- scripts run only if the exact script path is in the skill's
  ``permissions.scripts`` allowlist, inside the sandbox, with the
  skill's ``max_script_seconds`` as the timeout;
- per-skill token budgets (manifest ``budget.max_tokens_per_run``)
  are enforced alongside run-level and per-agent budgets;
- approval gates come from the plan (agent gates + skill gates); a
  denial halts the run as ``blocked_approval``.

Every step appends a StepTrace (skill, provider, tokens, cost,
attempts, status) — traces are the episodes the learning loop will
mine, so nothing about a run exists only in a log line.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

from .compiler import compile_plan
from .planner import resolve_expression
from .providers import ProviderError, StepRequest
from .registry import AgentRegistry
from .tools import (CalculatorTool, DataLookupTool, DocSearchTool,
                    FileReaderTool, FileWriterTool, ScriptRunnerTool,
                    ToolBox, ToolError)
from .workflow import PlanStep, WorkflowPlan

# The local tool each action needs (the plugin-layer verb's reach).
ACTION_TOOL = {"research": "doc_search", "lookup": "data_lookup",
               "compute": "calculator", "publish": "file_writer",
               "script": "script_runner", "synthesize": None, "write": None}

TERMINAL_OK = ("ok", "skipped")


@dataclass
class StepTrace:
    step_id: str
    agent: str
    action: str
    skill: str | None
    provider: str
    status: str            # ok | failed | denied | blocked | skipped |
                           # permission_denied | budget_blocked
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    attempts: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        return vars(self).copy()


@dataclass
class RunRecord:
    task_id: str
    plan: WorkflowPlan
    status: str = "running"      # completed | partial | failed |
                                 # blocked_approval | budget_exceeded
    traces: list = field(default_factory=list)
    replans: list = field(default_factory=list)
    final_output: str = ""
    results: dict = field(default_factory=dict)
    resolution_log: list = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(t.tokens_in + t.tokens_out for t in self.traces)

    @property
    def total_cost_usd(self) -> float:
        return sum(t.cost_usd for t in self.traces)

    @property
    def steps_executed(self) -> int:
        return sum(1 for t in self.traces if t.status == "ok")

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "status": self.status,
                "plan": self.plan.to_dict(),
                "plan_hash": self.plan.plan_hash(),
                "traces": [t.to_dict() for t in self.traces],
                "replans": self.replans,
                "total_tokens": self.total_tokens,
                "total_cost_usd": round(self.total_cost_usd, 6),
                "final_output": self.final_output,
                "resolution_log": self.resolution_log}


class BudgetGovernor:
    """Reserves estimated spend before a step starts; settles after."""

    def __init__(self, run_cap_tokens: int | None = None):
        self.run_cap = run_cap_tokens
        self.agent_spend: dict[str, int] = {}
        self.skill_spend: dict[str, int] = {}
        self.agent_caps: dict[str, int] = {}
        self.skill_caps: dict[str, int] = {}
        self.total_spend = 0

    def configure_agent(self, name: str, cap: int | None):
        if cap is not None:
            self.agent_caps[name] = cap

    def configure_skill(self, name: str, cap: int | None):
        if cap is not None:
            self.skill_caps[name] = cap

    def reserve(self, agent: str, skill: str | None, est: int) -> str | None:
        """Returns a refusal reason, or None when the spend is allowed."""
        if self.run_cap is not None and self.total_spend + est > self.run_cap:
            return f"run budget: {self.total_spend}+{est} > cap {self.run_cap}"
        cap = self.agent_caps.get(agent)
        if cap is not None and self.agent_spend.get(agent, 0) + est > cap:
            return (f"agent budget: {agent} "
                    f"{self.agent_spend.get(agent, 0)}+{est} > cap {cap}")
        if skill:
            scap = self.skill_caps.get(skill)
            if scap is not None and self.skill_spend.get(skill, 0) + est > scap:
                return (f"skill budget: {skill} "
                        f"{self.skill_spend.get(skill, 0)}+{est} > cap {scap}")
        return None

    def settle(self, agent: str, skill: str | None, tokens: int):
        self.total_spend += tokens
        self.agent_spend[agent] = self.agent_spend.get(agent, 0) + tokens
        if skill:
            self.skill_spend[skill] = self.skill_spend.get(skill, 0) + tokens


class ManagedRuntime:
    def __init__(self, registry: AgentRegistry, providers: dict, library,
                 chunks, metric_rows, sandbox_dir: str,
                 approver=None,               # fn(step, record) -> bool
                 budget_tokens: int | None = None,
                 sequential: bool = False,
                 on_trace=None):              # fn(trace_dict) -> None
        self.registry = registry
        self.providers = providers
        self.library = library
        self.sandbox_dir = sandbox_dir
        self.approver = approver or (lambda step, record: True)
        self.sequential = sequential
        self.on_trace = on_trace
        self._base_tools = {
            "calculator": CalculatorTool(),
            "doc_search": DocSearchTool(chunks),
            "data_lookup": DataLookupTool(metric_rows),
            "file_writer": FileWriterTool(sandbox_dir),
            "file_reader": FileReaderTool(sandbox_dir),
        }
        self._budget_cap = budget_tokens

    # -- provider selection -------------------------------------------------------
    def _provider_for(self, agent_name: str):
        pref = self.registry.get(agent_name).provider
        if pref in self.providers:
            return self.providers[pref]
        return next(iter(self.providers.values()))

    # -- permission boundary ---------------------------------------------------------
    def _toolbox_for(self, step: PlanStep) -> ToolBox:
        """Build the step's ToolBox, enforcing the skill's manifest.

        Raises PermissionError with a precise reason when the governing
        skill does not grant what the step's action needs."""
        agent = self.registry.get(step.agent)
        needed = ACTION_TOOL[step.action]
        available = dict(self._base_tools)
        if step.skill:
            pkg = self.library.get(step.skill)
            granted = pkg.manifest.granted_local_tools()
            allowed = tuple(t for t in agent.tools if t in granted)
            if needed and needed not in allowed:
                raise PermissionError(
                    f"skill {step.skill} does not grant tool {needed} "
                    f"(grants: {sorted(granted)}); step {step.id} refused")
            if step.action == "script":
                script = step.params.get("script", "")
                if script not in pkg.manifest.perm_scripts:
                    raise PermissionError(
                        f"script {script} not in {step.skill}'s "
                        f"permissions.scripts {pkg.manifest.perm_scripts}")
                available["script_runner"] = ScriptRunnerTool(
                    {script: os.path.join(pkg.path, script)},
                    self.sandbox_dir,
                    timeout_s=pkg.manifest.budget_script_seconds or 30)
            if step.action == "publish" and pkg.manifest.perm_fs_write:
                fname = step.params.get("filename", "")
                # "" or "." as a declared scope means the sandbox root.
                if not any(w in ("", ".") or fname == w
                           or fname.startswith(w.rstrip("/") + "/")
                           for w in pkg.manifest.perm_fs_write):
                    raise PermissionError(
                        f"publish target {fname} outside {step.skill}'s "
                        f"declared write scopes {pkg.manifest.perm_fs_write}")
        else:
            allowed = tuple(agent.tools)
            if step.action == "script":
                raise PermissionError("ungoverned steps may not run scripts")
        box_tools = [t for t in allowed if t in available]
        return ToolBox.build(tuple(box_tools), available)

    # -- public entry ------------------------------------------------------------------
    def run(self, plan: WorkflowPlan) -> RunRecord:
        return asyncio.run(self._run(plan))

    async def _run(self, plan: WorkflowPlan) -> RunRecord:
        plan.validate()
        record = RunRecord(task_id=plan.task_id, plan=plan)
        governor = BudgetGovernor(self._budget_cap)
        for name in self.registry.names():
            governor.configure_agent(name, self.registry.get(name).max_tokens_per_run)
        skills_in_plan = {s.skill for s in plan.steps if s.skill}
        for name in skills_in_plan:
            try:
                governor.configure_skill(
                    name, self.library.get(name).manifest.budget_tokens_per_run)
            except Exception:
                pass
        state = {"results": {}, "traces": []}
        completed: set = set()

        async def step_fn(step: PlanStep, _state):
            # Pregel re-triggers a node as each dependency channel
            # updates, so a node can be invoked before ALL its deps
            # have committed, and again afterwards. Invocations with
            # incomplete deps are spurious early triggers: defer them
            # silently; the invocation after the final dep commits
            # does the real work. A completed step never re-executes.
            if step.id in completed:
                return {"results": {}, "traces": []}
            if any(dep not in _state["results"] for dep in step.depends_on):
                return {"results": {}, "traces": []}
            out = await self._execute_step(step, record, governor, _state["results"])
            completed.add(step.id)
            state["results"].update(out["results"])
            state["traces"].extend(out["traces"])
            return out

        graph = compile_plan(plan, step_fn, sequential=self.sequential)
        t0 = time.time()
        await graph.ainvoke({"results": {}, "traces": []})
        record.results = state["results"]
        # Steps that never executed (a dependency failed / was denied /
        # was permission-refused) get an explicit blocked trace — a
        # missing step must be visible, never silent.
        traced = {t.step_id for t in state["traces"]}
        for s in plan.steps:
            if s.id not in traced:
                bt = StepTrace(step_id=s.id, agent=s.agent, action=s.action,
                               skill=s.skill,
                               provider=self._provider_for(s.agent).name,
                               status="blocked",
                               detail="a dependency did not complete")
                state["traces"].append(bt)
                if self.on_trace:
                    self.on_trace(bt.to_dict())
        order = {s.id: i for i, s in enumerate(plan.steps)}
        record.traces = sorted(state["traces"],
                               key=lambda t: order.get(t.step_id, 99))

        statuses = {t.step_id: t.status for t in record.traces}
        if any(t.status == "denied" for t in record.traces):
            record.status = "blocked_approval"
        elif any(t.status == "budget_blocked" for t in record.traces) \
                and governor.run_cap is not None:
            record.status = "budget_exceeded"
        elif all(statuses.get(s.id) in TERMINAL_OK for s in plan.steps):
            record.status = "completed"
        elif any(statuses.get(s.id) == "ok" for s in plan.steps):
            record.status = "partial"
        else:
            record.status = "failed"
        write = record.results.get("write")
        record.final_output = write["text"] if write else ""
        return record

    # -- one step ----------------------------------------------------------------------
    async def _execute_step(self, step: PlanStep, record: RunRecord,
                            governor: BudgetGovernor, results: dict) -> dict:
        provider = self._provider_for(step.agent)
        trace = StepTrace(step_id=step.id, agent=step.agent, action=step.action,
                          skill=step.skill, provider=provider.name, status="ok")

        def emit(status, detail=""):
            trace.status = status
            trace.detail = detail
            if self.on_trace:
                self.on_trace(trace.to_dict())
            return {"results": {}, "traces": [trace]}

        # dependencies must have succeeded
        for dep in step.depends_on:
            if dep not in results:
                return emit("blocked", f"dependency {dep} unavailable")

        # approval gate
        if step.sensitive and not self.approver(step, record):
            return emit("denied", "human approver denied this step")

        # permission boundary
        try:
            box = self._toolbox_for(step)
        except PermissionError as exc:
            return emit("permission_denied", str(exc))

        # build the request
        pkg = None
        if step.skill:
            try:
                pkg = self.library.get(step.skill)
            except Exception:
                pkg = None
        params = dict(step.params)
        if step.action == "compute" and params.pop("_ref_labels", None):
            label_to_id = step.params.get("_ref_labels", {})
            try:
                params["expression"] = resolve_expression(
                    params["expression"], results, label_to_id)
            except KeyError as exc:
                return emit("failed", str(exc))
        sections = tuple(params.pop("output_sections", []) or
                         (pkg.manifest.output_sections if pkg else []))
        # Context = everything gathered so far in this run (the graph
        # state accumulates all completed steps), not only direct deps.
        context = {k: v["text"] for k, v in results.items()}
        req = StepRequest(
            agent=step.agent, action=step.action, instruction=step.instruction,
            skill=step.skill,
            skill_instructions=(pkg.body if pkg else ""),
            context=context, params=params, output_sections=sections)

        est = provider.estimate_tokens(req)
        refusal = governor.reserve(step.agent, step.skill, est)
        if refusal:
            return emit("budget_blocked", refusal)

        attempts = 0
        current_agent = step.agent
        replanned = False
        while True:
            attempts += 1
            try:
                result = provider.execute(req, box)
                break
            except ProviderError as exc:
                if attempts < 2:
                    continue                      # one transient retry
                if not replanned:
                    backups = [a for a in self.registry.with_action(
                        step.action, exclude=(current_agent,))]
                    if backups:
                        current_agent = backups[0].name
                        req.agent = current_agent
                        provider = self._provider_for(current_agent)
                        replanned = True
                        record.replans.append(
                            f"step {step.id}: {step.agent} -> {current_agent} "
                            f"after provider failure ({exc})")
                        attempts = 0
                        continue
                if step.optional:
                    trace.attempts = attempts
                    return emit("skipped", f"optional step failed: {exc}")
                trace.attempts = attempts
                governor.settle(step.agent, step.skill, 0)
                return emit("failed", str(exc))
            except ToolError as exc:
                trace.attempts = attempts
                return emit("failed", str(exc))

        trace.attempts = attempts
        trace.agent = current_agent
        trace.provider = provider.name
        trace.tokens_in = result.tokens_in
        trace.tokens_out = result.tokens_out
        trace.latency_s = result.latency_s
        trace.cost_usd = (result.tokens_in * provider.price_in
                          + result.tokens_out * provider.price_out) / 1000.0
        governor.settle(current_agent, step.skill,
                        result.tokens_in + result.tokens_out)
        if self.on_trace:
            self.on_trace(trace.to_dict())
        return {"results": {step.id: {"text": result.text, **result.data}},
                "traces": [trace]}
