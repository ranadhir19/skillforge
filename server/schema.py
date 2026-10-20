"""GraphQL schema (Strawberry) for SkillForge.

The GraphQL layer is the *query* surface of the platform (design
Part 3.6): library browsing, skill provenance and permissions, run
traces, episodes, and the audit chain; plus the two mutations the UI
needs (trigger a run, change a lifecycle state) and a subscription
that streams step traces as a run executes. File-moving operations
(zip import/export) and the staged creation gate live on REST
(server/app.py) — GraphQL is the wrong shape for uploads.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import typing

import strawberry


@strawberry.type
class SkillType:
    name: str
    version: str
    lifecycle: str
    description: str
    tools: list[str]
    scripts: list[str]
    network: str
    fs_write: list[str]
    approval_required_for: list[str]
    composes: list[str]
    conflicts: list[str]
    governs: list[str]
    sections: list[str]
    trigger_examples: list[str]
    trigger_counter_examples: list[str]
    author: str
    origin: str
    content_hash: str


@strawberry.type
class TraceType:
    step_id: str
    agent: str
    action: str
    skill: typing.Optional[str]
    provider: str
    status: str
    tokens: int
    cost_usd: float
    attempts: int
    detail: str


@strawberry.type
class RunType:
    task_id: str
    status: str
    plan_hash: str
    primary_skill: typing.Optional[str]
    active_skills: list[str]
    total_tokens: int
    total_cost_usd: float
    final_output: str
    resolution_log: list[str]
    traces: list[TraceType]


@strawberry.type
class EpisodeType:
    episode_id: str
    task: str
    shape: str
    skills_used: list[str]
    provider: str
    status: str
    outcome_success: typing.Optional[bool]
    total_tokens: int


@strawberry.type
class AuditEntryType:
    seq: int
    event: str
    skill: typing.Optional[str]
    hash: str


@strawberry.type
class EvalSummaryType:
    skill: str
    provider: str
    total: int
    passed: int
    pass_rate: float


def skill_type(pkg) -> SkillType:
    m = pkg.manifest
    prov = pkg.provenance or {}
    return SkillType(
        name=pkg.name, version=m.version, lifecycle=m.lifecycle,
        description=pkg.description, tools=m.granted_tool_refs,
        scripts=m.perm_scripts, network=m.perm_network,
        fs_write=m.perm_fs_write,
        approval_required_for=m.approval_required_for,
        composes=m.composes, conflicts=m.conflicts, governs=m.governs,
        sections=m.output_sections,
        trigger_examples=m.trigger_examples,
        trigger_counter_examples=m.trigger_counter_examples,
        author=prov.get("author", "unknown"),
        origin=prov.get("origin", "unknown"),
        content_hash=pkg.content_hash())


def run_type(bundle) -> RunType:
    rec = bundle["record"]
    res = bundle["resolution"]
    return RunType(
        task_id=rec.task_id, status=rec.status,
        plan_hash=rec.plan.plan_hash(), primary_skill=res.primary,
        active_skills=res.names(), total_tokens=rec.total_tokens,
        total_cost_usd=round(rec.total_cost_usd, 6),
        final_output=rec.final_output, resolution_log=res.log,
        traces=[TraceType(step_id=t.step_id, agent=t.agent, action=t.action,
                          skill=t.skill, provider=t.provider, status=t.status,
                          tokens=t.tokens_in + t.tokens_out,
                          cost_usd=round(t.cost_usd, 6), attempts=t.attempts,
                          detail=t.detail) for t in rec.traces])


def get_platform(info) -> object:
    return info.context["platform"]


@strawberry.type
class Query:
    @strawberry.field
    def skills(self, info: strawberry.Info, lifecycle: typing.Optional[str] = None) -> list[SkillType]:
        plat = get_platform(info)
        return [skill_type(p) for p in plat.library.all()
                if lifecycle is None or p.lifecycle == lifecycle]

    @strawberry.field
    def skill(self, info: strawberry.Info, name: str) -> typing.Optional[SkillType]:
        plat = get_platform(info)
        try:
            return skill_type(plat.library.get(name))
        except Exception:
            return None

    @strawberry.field
    async def skill_evals(self, info: strawberry.Info, name: str,
                          provider: str = "stub-pro") -> typing.Optional[EvalSummaryType]:
        # Eval suites run agent workloads (asyncio.run inside the
        # runtime) — offload to a worker thread, never the event loop.
        plat = get_platform(info)
        try:
            pkg = plat.library.get(name)
        except Exception:
            return None
        rep = await asyncio.to_thread(plat.evaluator().run_package, pkg,
                                      provider=provider)
        return EvalSummaryType(skill=name, provider=provider, total=rep.total,
                               passed=rep.passed,
                               pass_rate=round(rep.pass_rate, 4))

    @strawberry.field
    def episodes(self, info: strawberry.Info, limit: int = 20) -> list[EpisodeType]:
        plat = get_platform(info)
        out = []
        for e in plat.episodes.all()[-limit:]:
            out.append(EpisodeType(
                episode_id=e["episode_id"], task=e["task"], shape=e["shape"],
                skills_used=e.get("skills_used", []), provider=e["provider"],
                status=e["status"],
                outcome_success=e.get("outcome", {}).get("success"),
                total_tokens=e.get("total_tokens", 0)))
        return out

    @strawberry.field
    def audit(self, info: strawberry.Info, limit: int = 20) -> list[AuditEntryType]:
        plat = get_platform(info)
        return [AuditEntryType(seq=e["seq"], event=e["event"],
                               skill=(e.get("payload") or {}).get("skill"),
                               hash=e["hash"])
                for e in plat.audit.entries()[-limit:]]

    @strawberry.field
    def audit_chain_valid(self, info: strawberry.Info) -> bool:
        return get_platform(info).audit.verify_chain()


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def trigger_run(self, info: strawberry.Info, task: str, provider: str = "stub-pro",
                          auto_approve: bool = True,
                          pin_skill: typing.Optional[str] = None) -> RunType:
        # Same offload as skill_evals: the runtime owns an event loop.
        plat = get_platform(info)
        approver = (lambda step, record: True) if auto_approve else \
            (lambda step, record: step.action not in ("publish",))
        pins = (pin_skill,) if pin_skill else ()
        bundle = await asyncio.to_thread(plat.run_task, task,
                                         provider=provider, approver=approver,
                                         pins=pins)
        info.context["runs"][bundle["record"].plan.plan_hash()] = bundle
        return run_type(bundle)

    @strawberry.mutation
    def set_lifecycle(self, info: strawberry.Info, name: str, state: str) -> SkillType:
        plat = get_platform(info)
        pkg = plat.library.set_lifecycle(name, state, actor="graphql")
        return skill_type(pkg)


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def run_events(self, info: strawberry.Info, task: str,
                         provider: str = "stub-pro") -> typing.AsyncGenerator[TraceType, None]:
        """Stream step traces as a run executes. The run happens on a
        worker thread (the runtime is synchronous); traces cross into
        the event loop through a queue."""
        plat = get_platform(info)
        q: "queue.Queue" = queue.Queue()
        done = threading.Event()

        def on_trace(td: dict):
            q.put(td)

        def work():
            try:
                plat.run_task(task, provider=provider, on_trace=on_trace,
                              record_episode=True)
            finally:
                done.set()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while not done.is_set() or not q.empty():
            try:
                td = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)
                continue
            yield TraceType(step_id=td["step_id"], agent=td["agent"],
                            action=td["action"], skill=td["skill"],
                            provider=td["provider"], status=td["status"],
                            tokens=td["tokens_in"] + td["tokens_out"],
                            cost_usd=round(td["cost_usd"], 6),
                            attempts=td["attempts"], detail=td["detail"])
        thread.join(timeout=5)


schema = strawberry.Schema(query=Query, mutation=Mutation,
                           subscription=Subscription)
