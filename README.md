# SkillForge

**A model-agnostic, self-learning skill platform.** Skills are
portable packages — a standard `SKILL.md` plus a manifest that adds
what the base format leaves out: tested triggers with near-miss
counter-examples, capability requirements instead of model names,
*enforced* permissions, in-package evals, provenance, and a
lifecycle. Packages execute on a managed runtime (declared agents,
per-task LangGraph workflows, a provider seam with deterministic
offline tiers, budget governance, approval gates), and new skills are
created dynamically through a human-gated flow: draft → validate →
sandboxed trial → **human approval** → shadow → active.

Everything below runs **offline, with no API keys**. Key-gated
OpenAI/Anthropic adapters sit behind the same provider seam for
deployments that have keys.

## Quickstart

```bash
pip install -e .                      # core package (LangGraph, PyYAML)
python3 demo.py                       # full session, writes results/demo_run.json
python3 -m pytest tests/              # 36 tests
python3 validate.py                   # the harness: imports, tests, gates, docs
```

Run the demo UI (FastAPI + GraphQL backend, React frontend):

```bash
pip install -e ".[server]"
PYTHONPATH=src:. uvicorn server.app:app --port 8000     # API + GraphQL at /graphql
cd frontend && npm install && npm run dev               # UI (proxies to :8000)
```

Or a two-liner from Python (`examples/quickstart.py`):

```python
from skillforge import repo_platform
plat = repo_platform()
bundle = plat.run_task("Research the remote work policy: days, core hours, equipment")
print(bundle["resolution"].names(), bundle["record"].status)
```

## Measured results (from real runs — see results/results.md)

| Experiment | Result |
|---|---|
| E1 Trigger quality, whole library | 80 cases: TP 40, FP 0, FN 0, TN 40 — precision 1.0, recall 1.0 |
| E2 Eval matrix (100 cases) | stub-pro **100/100**; stub-basic **98/100** (the two failures are exact-figure cases — the basic tier's documented operand-rounding property) |
| E3 Approval gate | publish approved → `completed`; denied → `blocked_approval`, analysis intact |
| E4 Dynamic creation | `unit-economics-snapshot` created from one demonstration: trial 3/3, registered shadow, inert until promoted, then governed a run with verified figures |
| E5 Vanilla import | a SKILL.md-only folder imports with synthesised safe defaults (no tools, no network, sandbox-only) |

Full detail: `results/results.md`, `results/experiments.json`,
`results/demo_run.json`. Reproduce: `python3 experiments/run_experiments.py`.

## The starter library (20 skills)

Each is a real package under `library/`: `SKILL.md` + `skill.yaml` +
an eval suite (4 trigger cases incl. near-misses, 1 end-to-end task
case). Originals authored for this platform; the discipline set
adapts conventions of the public agent-skills ecosystem with
attribution in each package's `provenance.json`.

| Tier | Skills |
|---|---|
| Meta & discipline | skill-creator, verification-before-completion, grill-me, handoff |
| Engineering | test-driven-development, diagnosing-bugs, code-review, fix-failing-ci, resolve-merge-conflict, improve-codebase-architecture |
| Documents & data | pdf-extract-and-fill (ships a sandboxed script), spreadsheet-analysis (script + cross-check verifier), document-drafting, data-analysis |
| Web & research | webapp-testing, web-research |
| Platform & cloud | postgres-best-practices, deploy-checklist |
| Design & comms | frontend-design, internal-comms |

## How it works

- **Packages** — `src/skillforge/packages.py`; static contract in
  `src/skillforge/validate_pkg.py` (name/manifest sync, referenced
  files exist, every script declared). Design: docs/architecture.md.
  Authoring: docs/authoring-skills.md.
- **Resolution** — two stages (`src/skillforge/resolver.py`):
  deterministic shortlist (BM25-lite + hashed embeddings), then a
  reranker scoring examples against counter-examples with a
  dominance-scaled penalty. Hard gates after scoring: lifecycle,
  capabilities vs the bound provider, conflicts, pins, co-active cap.
  Every exclusion carries its reason.
- **Execution** — planner composes a skill-annotated DAG
  (`src/skillforge/planner.py`), compiled to LangGraph per plan
  (`src/skillforge/compiler.py`), executed by a governed runtime
  (`src/skillforge/runtime.py`): tool grants are the intersection of
  agent and skill manifests, scripts are allowlist-checked and
  sandboxed, budgets reserve before spending, approval gates halt
  runs as `blocked_approval`, failures retry then replan to the
  backup agent.
- **Episodes** — every run is stored as a mineable episode
  (`src/skillforge/episodes.py`): task shape signature, skills used,
  plan hash, traces, and an outcome labelled by a deterministic
  verifier or explicitly left unlabelled. This is the substrate the
  Phase 2 learning loop will mine.
- **Audit** — lifecycle events (create, approve, promote, import)
  go to a hash-chained append-only log; tampering is detectable.
- **Creation** — `src/skillforge/creator.py`: the offline drafter
  composes a package from a description + demonstration, with
  least-privilege defaults and starter evals derived from the
  demonstration. Nothing registers without the gate.
- **Serving** — `server/app.py` + `server/schema.py` (FastAPI,
  Strawberry GraphQL: library/provenance/traces/episodes queries,
  `triggerRun`/`setLifecycle` mutations, `runEvents` subscription;
  REST for `/health`, import/export, staged creation).
  `frontend/` is the React UI (Library, Run, Create screens).
  `render.yaml` wires both as Render services.

## Repo layout

```
src/skillforge/   core package (pip-installable)
library/          the 20 starter skill packages
server/           FastAPI + GraphQL serving layer
frontend/         React UI (Vite)
tests/            36 tests (core, library suites, creation, server)
experiments/      run_experiments.py → results/
docs/             architecture.md, authoring-skills.md
demo.py           end-to-end demo        validate.py   the harness
render.yaml       Render blueprint (API web service + static UI)
```

## Honest limits

- **The offline tiers execute procedure structure, not prose.**
  Scripted providers run a step's tools, sections and gates
  deterministically; a keyed model following the skill's instructions
  semantically is the same seam with a different provider — designed
  for, not measured here.
- **Trigger quality is measured on authored cases** (40 positives,
  40 near-misses written for this library), not an external
  benchmark. The suites are in the packages; judge them there.
- **Task-case fixtures are seeded and labelled as fixtures**
  (`src/skillforge/corpus.py`); evals verify behaviour against them,
  not against the live world.
- **Phase 2 (the self-learning loop) is designed, not built**: the
  episode store, holdout reporting and gate machinery it needs ship
  here; the miner/distiller do not. See docs/architecture.md.
- The demo data directory (`data/`) accumulates episodes and audit
  entries at runtime; on Render it is ephemeral by design.

## Validation

`python3 validate.py` — import/compile, the full test suite, the
standing employer-reference gate scan over sources, and
documentation/results consistency (including static validation of
all 20 library packages). It exits `HARNESS GREEN` or names the
failing stage. See VALIDATION.md for exactly what it does and does
not verify.
