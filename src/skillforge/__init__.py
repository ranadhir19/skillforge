"""SkillForge: a model-agnostic, self-learning skill platform.

Portable skill packages (SKILL.md + skill.yaml manifest: triggers,
capability requirements, enforced permissions, in-package evals,
provenance, lifecycle), a two-stage resolver, a governed LangGraph
runtime on a provider seam (deterministic offline tiers; key-gated
real providers), human-gated dynamic skill creation, and episode
storage structured for the Phase 2 learning loop.
"""

from .packages import Manifest, SkillPackage, load_package
from .validate_pkg import ValidationReport, validate_package
from .library import Library, permission_diff
from .resolver import Resolver, Resolution, DeterministicReranker
from .planner import SkillPlanner
from .runtime import ManagedRuntime, RunRecord, StepTrace, BudgetGovernor
from .registry import AgentRegistry, AgentSpec, default_registry
from .providers import (ScriptedProvider, StepRequest, StepResult,
                        ProviderError, provider_from_env)
from .workflow import PlanStep, WorkflowPlan
from .compiler import compile_plan
from .corpus import TaskSpec, demo_task
from .platform import Platform, repo_platform
from .audit import AuditLog
from .episodes import EpisodeStore
from .evals import EvalRunner, EvalReport
from .creator import SkillCreator, CreationResult

__version__ = "0.1.0"

__all__ = [
    "Manifest", "SkillPackage", "load_package",
    "ValidationReport", "validate_package",
    "Library", "permission_diff",
    "Resolver", "Resolution", "DeterministicReranker",
    "SkillPlanner", "ManagedRuntime", "RunRecord", "StepTrace",
    "BudgetGovernor", "AgentRegistry", "AgentSpec", "default_registry",
    "ScriptedProvider", "StepRequest", "StepResult", "ProviderError",
    "provider_from_env", "PlanStep", "WorkflowPlan", "compile_plan",
    "TaskSpec", "demo_task", "Platform", "repo_platform",
    "AuditLog", "EpisodeStore", "EvalRunner", "EvalReport",
    "SkillCreator", "CreationResult",
]
