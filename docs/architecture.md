# SkillForge architecture

SkillForge is a model-agnostic, self-learning **skill platform**. It
generalises the Agent Skills idea (a folder with a `SKILL.md`) beyond
any single vendor's runtime: skills are portable packages with
*enforced* permissions, *tested* triggers, capability requirements
instead of model names, provenance, and a lifecycle — executed on a
managed runtime (built on the open-managed-agents engine design:
declared agents, per-task workflow DAGs compiled to LangGraph at
runtime, a provider seam, budget governance, approval gates).

## The three layers (and what each is not)

| Layer | What it is | Examples here |
|---|---|---|
| **Plugins / tools** | Verbs and reach: callable capabilities with schemas | `native:calculator`, `native:doc_search`, `native:data_lookup`, `native:file_writer`, `native:script_runner`; external tools namespaced `mcp:<server>/<tool>` |
| **Skills** | Packaged procedural know-how: instructions + triggers + permissions + evals | the 20 packages under `library/` |
| **Memory** | Continuity across runs | episodes (trajectory + verifier-labelled outcome), the hash-chained audit log; Phase 2 adds episodic mining over the same store |

Skills reference tools; they never *are* the transport. A skill that
needs a tool the runtime cannot bind is excluded at resolution time
with the reason surfaced — never discovered mid-run.

## The package

```
name/
├── SKILL.md          frontmatter (name, description) + instruction body
├── skill.yaml        manifest (below)
├── scripts/          optional; allowlisted in the manifest, sandboxed
├── references/       optional; loaded on demand (progressive disclosure)
├── assets/           optional; templates and data files
├── evals/            cases.yaml (+ optional verifiers.py, holdout file)
└── provenance.json   platform-written: author, origin, trial scores
```

The manifest (`apiVersion: skillforge/v1`) adds what the base format
does not standardise: trigger examples **and counter-examples**,
`requires.capabilities` (never model names), a permission block
(tool/script allowlists, network mode, filesystem scopes,
approval-required actions), composition (`composes`/`conflicts`), a
per-run budget, the eval suite pointer with its pass bar, and the
lifecycle state: `draft | shadow | active | deprecated`, plus
`imported` for vanilla packages loaded with synthesised safe
defaults (no scripts, no network, sandbox-only writes).

Portable export strips `skill.yaml` + `provenance.json` and ships an
`EXPORT_NOTE.md` stating plainly what does not travel (enforcement,
evals, provenance) — the base format's guarantees end where its spec
ends, and the export says so.

## Resolution (two stages)

1. **Stage 1 — deterministic shortlist.** BM25-lite token overlap and
   a hashed-embedding cosine over each skill's metadata (name,
   description, trigger examples) produce ~12 candidates.
2. **Stage 2 — rerank.** The offline default is a deterministic
   reranker: example proximity + description proximity + stage-1
   evidence, minus a counter-example penalty scaled by *counter
   dominance* (how much better the nearest near-miss explains the
   task than the best positive example). A `ModelReranker` with the
   same interface ships for keyed deployments.

Hard gates then apply, in order: lifecycle (only `active` governs;
`shadow` is scored and logged, never governing), capability check
against the bound provider, declared conflicts (resolved by score =
specificity), user pins (win over everything except honesty: a pinned
skill missing capabilities proceeds only with a logged warning), and
a cap K=4 on co-active skills. Every decision is written to the
resolution log with its reason.

## Planning and execution

The planner composes a workflow DAG from the task and annotates each
step with its governing skill (the active skill whose `governs` list
covers the step's action; the primary skill governs synthesis and
writing). Steps are compiled to a LangGraph `StateGraph` at runtime
— no hand-written graph exists.

The runtime (adapted from open-managed-agents) enforces governance
at the tool boundary:

- a step's tool box is the intersection of the agent's grant and the
  governing skill's manifest grant; a step needing a tool its skill
  does not grant ends `permission_denied` — never silently re-routed;
- scripts run only if the exact path is in `permissions.scripts`,
  in a subprocess confined to the run sandbox, with the manifest's
  script timeout;
- publish targets must fall inside the skill's declared write scopes;
- budgets: run cap, per-agent caps, and per-skill manifest caps are
  reserved before each step and settled after;
- approval gates come from the agent spec and/or the skill manifest
  (`approval_required_for`); a denial halts the run as
  `blocked_approval`, with the analysis intact and the publish
  un-done;
- failures get one retry, then a replan onto the backup agent;
  dependents of a failed step are marked `blocked`, never skipped
  silently.

Every step appends a trace (skill, provider, tokens, cost, attempts,
status). Every run appends an **episode**: task, task *shape* (the
clustering signature), skills used, plan hash, traces, and an outcome
labelled by a deterministic verifier or left explicitly unlabelled.

## Providers

Providers are the only components that know how a step executes.
Two deterministic offline tiers ship (`stub-pro`, `stub-basic`) with
declared capability sets and strategy-level differences (retrieval
depth, arithmetic precision, synthesis selectivity) — the whole
platform, its tests, its evals and its demo run with no API keys.
Key-gated OpenAI/Anthropic REST adapters implement the same seam in
direct-completion mode and are never constructed without a key.

## Dynamic creation (Phase 1, shipped)

```
describe / demonstrate → draft → static validation → sandboxed
trial vs the draft's own evals → HUMAN GATE (plain-language
permission summary) → register as shadow → (separate act) promote
```

The offline drafter composes the package deterministically from a
description + one demonstration (its steps become the procedure; its
input/output pair seeds the starter evals). Least-privilege defaults:
no network, sandbox writes, only the tools the demonstration used.
Provenance is written at registration (author, origin, trial scores);
lifecycle events go to the hash-chained audit log.

## Serving

FastAPI hosts the core in-process. GraphQL (Strawberry) is the query
layer: library browsing, skill permissions/provenance, per-skill
eval summaries, episodes, audit — plus `triggerRun` and
`setLifecycle` mutations and a `runEvents` subscription streaming
step traces. REST carries `/health`, zip import/export, run
triggering by id, and the staged creation gate (`POST /skills/draft`
→ `POST /skills/{draft_id}/decide`) — the human decision is an
explicit call, never a server default. The React frontend (Library,
Run, Create screens) talks to the same surface. `render.yaml` wires
the two Render services.

## Phase 2 (designed, not built here)

The learning loop — mine episode clusters → distil candidate skills →
verify (static + replay incl. independently-authored holdout +
whole-library trigger regression) → human gate → promote
shadow→active — runs on the episode store this build ships. Its
guardrails are structural, not aspirational: a candidate never writes
its own exam, model judgement is never sole evidence for script or
write skills, and auto-promotion (when it ever ships) is limited to
instruction-only, read-only, no-script skills below a risk tier.
