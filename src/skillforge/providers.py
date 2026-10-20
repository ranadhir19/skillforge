"""Model providers: the model-agnostic seam of the platform.

Adapted from open-managed-agents' provider layer. A *provider* is the
only thing that knows how a step gets executed; plans, skills and the
runtime never name a model vendor. Two families ship here:

- ``ScriptedProvider`` — deterministic, offline, seeded stand-ins in
  two capability tiers (``stub-basic`` and ``stub-pro``). They execute
  each step *action* with explicit strategies over the real tools, so
  the whole platform runs — and every experiment reproduces — with no
  API keys. The tier differences are strategy differences (retrieval
  depth, arithmetic precision, synthesis selectivity), not coin flips.
  Honest scope: the scripted tiers execute a step's *procedure
  structure* (which tools, in what shape, with which output sections
  the governing skill declares). Following the skill's prose
  semantically is what a real model does through the same seam.

- ``OpenAIProvider`` / ``AnthropicProvider`` — thin REST adapters used
  only when the matching API key is in the environment. They run steps
  in *direct-completion* mode: the model receives the step instruction,
  the governing skill's loaded instructions, and gathered context, and
  answers in one completion. They are never constructed by the demo,
  the tests or the experiments unless a key is present.

Providers also declare a *capability set* (tool_calling, long_context,
vision, code_execution). Skill manifests declare required capabilities
— never model names — and the resolver checks the bound provider
against them (design Part 3.1).

Token counts are a deterministic function of text length
(``chars // 4``), so accounting is reproducible offline.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field

from .tools import ToolBox, ToolError


class ProviderError(Exception):
    """A provider failed to execute a step (retryable by the runtime)."""


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


# Simulated per-action latency in seconds (what a hosted model
# round-trip plus tool time feels like at this scale). Deterministic.
ACTION_LATENCY = {"research": 0.22, "lookup": 0.08, "compute": 0.12,
                  "synthesize": 0.18, "write": 0.10, "publish": 0.05,
                  "script": 0.06}

# Deterministic per-action token estimate used by the budget governor
# when reserving spend before a step starts.
ACTION_EST_TOKENS = {"research": 900, "lookup": 300, "compute": 500,
                     "synthesize": 1200, "write": 800, "publish": 200,
                     "script": 350}

ALL_CAPABILITIES = ("tool_calling", "long_context", "vision", "code_execution")


@dataclass
class StepRequest:
    agent: str
    action: str
    instruction: str
    skill: str | None = None                    # governing skill package name
    skill_instructions: str = ""                # loaded SKILL.md body (L2)
    context: dict = field(default_factory=dict)   # key -> text from prior steps
    params: dict = field(default_factory=dict)    # structured step parameters
    output_sections: tuple[str, ...] = ()         # declared by governing skill


@dataclass
class StepResult:
    text: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    data: dict = field(default_factory=dict)


class ScriptedProvider:
    """Deterministic offline provider with a named capability tier."""

    # price per 1K tokens (USD): stub-basic mimics a small hosted model
    # (~$0.20/$0.40 per 1M), stub-pro a frontier model (~$3/$15 per 1M)
    PRICES = {"stub-basic": (0.0002, 0.0004), "stub-pro": (0.003, 0.015)}
    CAPABILITIES = {"stub-basic": frozenset({"tool_calling"}),
                    "stub-pro": frozenset(ALL_CAPABILITIES)}

    def __init__(self, tier: str = "stub-pro", fail_agents=frozenset(),
                 flaky: dict | None = None):
        if tier not in self.PRICES:
            raise ValueError(f"unknown tier: {tier}")
        self.name = tier
        self.tier = tier
        self.capabilities = self.CAPABILITIES[tier]
        self.price_in, self.price_out = self.PRICES[tier]
        self._fail_agents = set(fail_agents)       # agents that always error
        self._flaky = dict(flaky or {})            # agent -> failures before success
        self._attempts: dict[str, int] = {}

    # -- failure injection (used by recovery tests) -------------------------
    def _maybe_fail(self, req: StepRequest):
        if req.agent in self._fail_agents:
            raise ProviderError(f"agent {req.agent} is down (injected)")
        left = self._flaky.get(req.agent, 0)
        if left > 0:
            self._flaky[req.agent] = left - 1
            raise ProviderError(f"agent {req.agent} transient failure (injected)")

    # -- action strategies ----------------------------------------------------
    def _research(self, req: StepRequest, box: ToolBox) -> StepResult:
        search = box.get("doc_search")
        k = 1 if self.tier == "stub-basic" else 3
        chunks = search.search(req.instruction, k=k)
        text = "\n".join(f"[{c.doc_id}] {c.text}" for c in chunks)
        return self._finish(req, text, {"chunks": [c.doc_id for c in chunks]})

    def _lookup(self, req: StepRequest, box: ToolBox) -> StepResult:
        lookup = box.get("data_lookup")
        p = req.params
        value = lookup.query(p["metric"], region=p.get("region"),
                             month=p.get("month"), agg=p.get("agg", "sum"))
        label = p.get("label", p["metric"])
        text = f"{label} = {value:.2f}"
        return self._finish(req, text, {"value": value, "label": label})

    def _compute(self, req: StepRequest, box: ToolBox) -> StepResult:
        calc = box.get("calculator")
        expr = req.params["expression"]
        if self.tier == "stub-basic":
            # basic tier rounds every literal operand to an integer first —
            # a real, deterministic precision loss on decimal arithmetic.
            expr = re.sub(r"\d+\.\d+", lambda m: str(round(float(m.group()))), expr)
        value = calc.run(expr)
        label = req.params.get("label", "result")
        text = f"{label} = {value:.2f}"
        return self._finish(req, text, {"value": value, "label": label})

    def _synthesize(self, req: StepRequest, box: ToolBox) -> StepResult:
        parts = [req.context[k] for k in sorted(req.context)]
        joined = "\n".join(parts)
        if self.tier == "stub-basic":
            text = joined[:400]
        else:
            sentences = re.split(r"(?<=[.!?])\s+", joined.replace("\n", " "))
            keep = [s for s in sentences
                    if re.search(r"\d", s) or s.strip().startswith("[")]
            text = " ".join(keep) if keep else joined[:400]
        return self._finish(req, text, {})

    def _write(self, req: StepRequest, box: ToolBox) -> StepResult:
        title = req.params.get("title", "Deliverable")
        body_parts = []
        if req.output_sections:
            # The governing skill declares the deliverable's structure;
            # the scripted executor fills the first section with the
            # full gathered context and the remaining sections from
            # individual sources (round-robin over sorted context
            # keys), so the artifact's *shape* is the skill's procedure
            # made visible. A real model fills the same sections
            # semantically.
            keys = sorted(req.context)
            joined = "\n\n".join(req.context[k] for k in keys)
            for i, section in enumerate(req.output_sections):
                if i == 0:
                    content = joined
                else:
                    content = req.context[keys[(i - 1) % len(keys)]] if keys else ""
                body_parts.append(f"## {section}\n{content}")
        else:
            body_parts = [f"## {k}\n{req.context[k]}" for k in sorted(req.context)]
        text = f"# {title}\n\n" + "\n\n".join(body_parts) + "\n"
        return self._finish(req, text, {})

    def _publish(self, req: StepRequest, box: ToolBox) -> StepResult:
        writer = box.get("file_writer")
        content = "\n\n".join(req.context[k] for k in sorted(req.context))
        path = writer.run(req.params["filename"], content)
        text = f"published to {path}"
        return self._finish(req, text, {"path": path})

    def _script(self, req: StepRequest, box: ToolBox) -> StepResult:
        runner = box.get("script_runner")
        out = runner.run(req.params["script"], req.params.get("payload", {}))
        label = req.params.get("label", req.params["script"])
        text = f"{label}: {out}"
        data = {}
        try:
            data = {"value": float(out.splitlines()[-1].split("=")[-1])}
        except (ValueError, IndexError):
            pass
        return self._finish(req, text, data)

    # -- plumbing -------------------------------------------------------------
    def _finish(self, req: StepRequest, text: str, data: dict) -> StepResult:
        ctx_text = "\n".join(req.context.values())
        return StepResult(text=text,
                          tokens_in=_tokens(req.instruction + req.skill_instructions
                                              + ctx_text),
                          tokens_out=_tokens(text),
                          latency_s=ACTION_LATENCY[req.action],
                          data=data)

    def execute(self, req: StepRequest, box: ToolBox) -> StepResult:
        self._attempts[req.agent] = self._attempts.get(req.agent, 0) + 1
        self._maybe_fail(req)
        handler = {"research": self._research, "lookup": self._lookup,
                   "compute": self._compute, "synthesize": self._synthesize,
                   "write": self._write, "publish": self._publish,
                   "script": self._script}.get(req.action)
        if handler is None:
            raise ProviderError(f"scripted provider cannot do action {req.action!r}")
        try:
            return handler(req, box)
        except ToolError as exc:
            raise ProviderError(str(exc)) from exc

    def estimate_tokens(self, req: StepRequest) -> int:
        return ACTION_EST_TOKENS[req.action]


# --------------------------------------------------------------------------
# Optional real-provider adapters (direct completion; key-gated)
# --------------------------------------------------------------------------

class _RESTProvider:
    """Base for hosted-model adapters. Never constructed without a key."""

    name = "rest"
    price_in = 0.0
    price_out = 0.0
    capabilities = frozenset(ALL_CAPABILITIES)

    def __init__(self, model: str, api_key: str):
        self.model = model
        self._key = api_key

    def estimate_tokens(self, req: StepRequest) -> int:
        return ACTION_EST_TOKENS[req.action]

    def _prompt(self, req: StepRequest) -> str:
        ctx = "\n\n".join(f"[{k}]\n{v}" for k, v in sorted(req.context.items()))
        skill_block = (f"\nGoverning skill: {req.skill}\n"
                       f"Skill instructions:\n{req.skill_instructions}\n"
                       if req.skill else "")
        return (f"You are an executor agent performing one workflow step.\n"
                f"Action: {req.action}\nInstruction: {req.instruction}\n"
                f"{skill_block}\nContext from previous steps:\n{ctx}\n\n"
                f"Return only the step output.")

    def execute(self, req: StepRequest, box: ToolBox) -> StepResult:  # pragma: no cover
        raise NotImplementedError

    def _post(self, url: str, payload: dict, headers: dict) -> dict:  # pragma: no cover
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())


class OpenAIProvider(_RESTProvider):  # pragma: no cover - key-gated
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not set")
        super().__init__(model, key)
        self.price_in, self.price_out = 0.00015, 0.0006  # USD per 1K tokens

    def execute(self, req: StepRequest, box: ToolBox) -> StepResult:
        import time
        t0 = time.time()
        out = self._post("https://api.openai.com/v1/chat/completions",
                         {"model": self.model,
                          "messages": [{"role": "user", "content": self._prompt(req)}]},
                         {"Authorization": f"Bearer {self._key}"})
        text = out["choices"][0]["message"]["content"]
        usage = out.get("usage", {})
        return StepResult(text=text,
                          tokens_in=usage.get("prompt_tokens", _tokens(req.instruction)),
                          tokens_out=usage.get("completion_tokens", _tokens(text)),
                          latency_s=time.time() - t0, data={})


class AnthropicProvider(_RESTProvider):  # pragma: no cover - key-gated
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str | None = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        super().__init__(model, key)
        self.price_in, self.price_out = 0.003, 0.015  # USD per 1K tokens

    def execute(self, req: StepRequest, box: ToolBox) -> StepResult:
        import time
        t0 = time.time()
        out = self._post("https://api.anthropic.com/v1/messages",
                         {"model": self.model, "max_tokens": 1024,
                          "messages": [{"role": "user", "content": self._prompt(req)}]},
                         {"x-api-key": self._key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in out.get("content", []))
        usage = out.get("usage", {})
        return StepResult(text=text,
                          tokens_in=usage.get("input_tokens", _tokens(req.instruction)),
                          tokens_out=usage.get("output_tokens", _tokens(text)),
                          latency_s=time.time() - t0, data={})


def provider_from_env(name: str):  # pragma: no cover - key-gated convenience
    """Build a provider by name; scripted tiers need no key."""
    if name in ScriptedProvider.PRICES:
        return ScriptedProvider(name)
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"unknown provider: {name}")
