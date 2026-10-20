"""The executor-agent registry: agents are *declared*, not coded.

Carried over from open-managed-agents with one conceptual shift (per
the design document, Part 3.2): in the managed-agents platform the
registry declared agents with hard-coded skill verbs. Here the verbs
are *actions* (the plugin layer), and procedural know-how lives in
skill *packages* (see packages.py). An ``AgentSpec`` is pure data —
name, role, instructions, the actions it can perform, the tools it may
touch, its provider, and its own approval-gated actions. Skill-level
gates and permissions come from the governing skill's manifest and
are enforced by the runtime on top of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .workflow import ACTIONS


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    instructions: str
    actions: tuple[str, ...]
    tools: tuple[str, ...]
    provider: str = "stub-pro"               # provider preference
    approval_actions: tuple[str, ...] = ()   # actions gated on human approval
    max_tokens_per_run: int | None = None    # per-agent budget cap (tokens)

    def __post_init__(self):
        bad = [a for a in self.actions if a not in ACTIONS]
        if bad:
            raise ValueError(f"agent {self.name}: unknown actions {bad}")
        bad = [a for a in self.approval_actions if a not in self.actions]
        if bad:
            raise ValueError(f"agent {self.name}: approval actions not in actions {bad}")


@dataclass
class AgentRegistry:
    _agents: dict = field(default_factory=dict)

    def register(self, spec: AgentSpec) -> AgentSpec:
        if spec.name in self._agents:
            raise ValueError(f"duplicate agent: {spec.name}")
        self._agents[spec.name] = spec
        return spec

    def get(self, name: str) -> AgentSpec:
        if name not in self._agents:
            raise KeyError(f"unknown agent: {name}")
        return self._agents[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._agents))

    def with_action(self, action: str, exclude: tuple[str, ...] = ()) -> list[AgentSpec]:
        """Agents that can perform ``action``, in registration order."""
        return [a for a in self._agents.values()
                if action in a.actions and a.name not in exclude]

    def __len__(self):
        return len(self._agents)


def default_registry() -> AgentRegistry:
    """The demo fleet: a primary executor on the pro tier and a backup
    on the basic tier (used by replans). The backup's publish action is
    human-gated at the agent level as well as the skill level."""
    reg = AgentRegistry()
    reg.register(AgentSpec(
        name="executor", role="skill executor",
        instructions="Execute workflow steps under the governing skill's "
                     "instructions and permissions.",
        actions=ACTIONS,
        tools=("doc_search", "data_lookup", "calculator", "file_writer",
               "file_reader", "script_runner"),
        provider="stub-pro"))
    reg.register(AgentSpec(
        name="executor-backup", role="skill executor (backup)",
        instructions="Backup executor; same tools, cheaper provider tier.",
        actions=ACTIONS,
        tools=("doc_search", "data_lookup", "calculator", "file_writer",
               "file_reader", "script_runner"),
        provider="stub-basic",
        approval_actions=("publish",)))
    return reg
