"""The Platform facade: wires library, resolver, planner, runtime,
episode store and audit chain into the object the demo, the server
and the tests all drive. One construction path, so what the demo
shows is what the API serves is what the tests measure.
"""

from __future__ import annotations

import os

from .audit import AuditLog
from .corpus import CHUNKS, METRIC_ROWS, TaskSpec
from .episodes import EpisodeStore, task_shape
from .library import Library
from .planner import SkillPlanner
from .providers import ScriptedProvider, provider_from_env
from .registry import default_registry
from .resolver import Resolver
from .runtime import ManagedRuntime


class Platform:
    def __init__(self, library_roots: list[str], data_dir: str,
                 sandbox_dir: str | None = None):
        self.library_roots = [os.path.abspath(r) for r in library_roots]
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.sandbox_dir = os.path.abspath(
            sandbox_dir or os.path.join(self.data_dir, "sandbox"))
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self.audit = AuditLog(os.path.join(self.data_dir, "audit.jsonl"))
        self.episodes = EpisodeStore(os.path.join(self.data_dir, "episodes.jsonl"))
        self.library = Library(self.library_roots, audit=self.audit)
        self.registry = default_registry()
        self.resolver = Resolver(self.library)
        self.planner = SkillPlanner(self.registry, self.library)

    # -- providers ---------------------------------------------------------------
    def make_providers(self, name: str) -> dict:
        """A provider map for one run. Scripted tiers are keyed by the
        agent preference names; choosing a tier maps every agent to a
        fresh instance of it (a true provider swap). Real providers
        are built only when their key is present (provider_from_env
        raises otherwise)."""
        if name in ScriptedProvider.PRICES:
            return {"stub-pro": ScriptedProvider(name),
                    "stub-basic": ScriptedProvider(name)}
        prov = provider_from_env(name)
        return {"stub-pro": prov, "stub-basic": prov}

    def provider_capabilities(self, name: str):
        if name in ScriptedProvider.CAPABILITIES:
            return ScriptedProvider.CAPABILITIES[name]
        return provider_from_env(name).capabilities

    # -- running ---------------------------------------------------------------------
    def run_task(self, task, provider: str = "stub-pro", approver=None,
                 budget_tokens: int | None = None, pins: tuple = (),
                 sandbox_dir: str | None = None, record_episode: bool = True,
                 verifier=None, on_trace=None) -> dict:
        """Resolve -> plan -> run -> episode. ``task`` is a TaskSpec or
        free text. ``verifier`` (optional) labels the episode outcome:
        fn(task, record) -> (success: bool, detail: str). Without a
        verifier the outcome stays unlabelled — never assumed."""
        sandbox = sandbox_dir or self.sandbox_dir
        if isinstance(task, str):
            task_text = task
            task_id = "adhoc"
        else:
            task_text = task.goal
            task_id = task.task_id
        caps = self.provider_capabilities(provider)
        all_pins = list(pins)
        if not isinstance(task, str) and task.skill_hint:
            all_pins.append(task.skill_hint)
        resolution = self.resolver.resolve(task_text,
                                           provider_capabilities=caps,
                                           pins=tuple(all_pins))
        if isinstance(task, str):
            plan = self.planner.plan_text(task_text, resolution, task_id=task_id)
        else:
            plan = self.planner.plan_task(task, resolution)
        runtime = ManagedRuntime(self.registry, self.make_providers(provider),
                                 self.library, CHUNKS, METRIC_ROWS, sandbox,
                                 approver=approver, budget_tokens=budget_tokens,
                                 on_trace=on_trace)
        record = runtime.run(plan)
        record.resolution_log = resolution.log
        bundle = {"resolution": resolution, "plan": plan, "record": record}
        if record_episode:
            success, vdetail = (None, "")
            if verifier is not None:
                success, vdetail = verifier(task, record)
            actions = sorted({s.action for s in plan.steps})
            episode = {
                "task_id": task_id, "task": task_text,
                "shape": task_shape(task_text, actions, resolution.names()),
                "skills_used": resolution.names(),
                "primary_skill": resolution.primary,
                "provider": provider,
                "plan_hash": plan.plan_hash(),
                "status": record.status,
                "outcome": {"success": success, "verifier": vdetail},
                "total_tokens": record.total_tokens,
                "total_cost_usd": round(record.total_cost_usd, 6),
                "traces": [{"step": t.step_id, "action": t.action,
                            "skill": t.skill, "status": t.status}
                           for t in record.traces],
            }
            bundle["episode"] = self.episodes.append(episode)
        return bundle

    # -- variants ---------------------------------------------------------------------
    def ephemeral(self, library_roots: list[str]) -> "Platform":
        """A sibling platform over different library roots (trials),
        sharing this platform's data dir conventions but writing
        episodes/audit to a throwaway location."""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="skillforge-ephemeral-")
        plat = Platform.__new__(Platform)
        plat.library_roots = [os.path.abspath(r) for r in library_roots]
        plat.data_dir = tmp
        plat.sandbox_dir = os.path.join(tmp, "sandbox")
        os.makedirs(plat.sandbox_dir, exist_ok=True)
        plat.audit = AuditLog(os.path.join(tmp, "audit.jsonl"))
        plat.episodes = EpisodeStore(os.path.join(tmp, "episodes.jsonl"))
        plat.library = Library(plat.library_roots, audit=plat.audit)
        plat.registry = default_registry()
        plat.resolver = Resolver(plat.library)
        plat.planner = SkillPlanner(plat.registry, plat.library)
        return plat

    # -- creation -----------------------------------------------------------------------
    def creator(self):
        from .creator import SkillCreator
        return SkillCreator(self)

    def evaluator(self):
        from .evals import EvalRunner
        return EvalRunner(self)


def repo_platform(root: str | None = None) -> Platform:
    """The platform over this repository's own library/ and data/."""
    root = root or os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))
    return Platform([os.path.join(root, "library")],
                    os.path.join(root, "data"))
