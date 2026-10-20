# Validation

`python3 validate.py` is this repository's test harness. It is
deterministic and offline, and it prints exactly one final line:
`HARNESS GREEN` (exit 0) or `HARNESS RED: <stages>` (exit 1).

## Stages

1. **import/compile** — `compileall` over `src/`, `tests/`, `server/`,
   `examples/`, `experiments/` and `demo.py`; then, in a clean
   subprocess, import the `skillforge` package and every one of its
   modules, plus `server.app` and `server.schema`.
2. **test suite** — the full pytest suite (36 tests) in a subprocess:
   package/validator/library unit tests, resolver and runtime
   governance (permission refusals, approval denial, budget block,
   provider swap, replan recovery), the whole starter library's eval
   suites on the pro tier, the basic tier's documented precision gap,
   dynamic creation end-to-end (including the denial path), and the
   FastAPI/GraphQL server through its real HTTP layer.
3. **employer-reference scan** — the standing gate scanner
   (`~/workspace/github-fis-watch/fis_scan.py`, path overridable via
   the `FIS_SCAN` environment variable) over the repository's
   *sources*: `src/`, `library/`, `tests/`, `server/`, `frontend/src/`,
   `docs/`, `examples/`, `experiments/` and the root documents.
   Candidates are judged in context by the rules below; a REAL
   reference fails the stage. Build artifacts (`frontend/dist`,
   `node_modules`) and runtime data (`data/*.jsonl`,
   `results/sandbox`) are not scanned: they are generated, and the
   sources that generate them are.
4. **docs/results consistency** — every `docs/…`, `results/…`,
   `examples/…`, `experiments/…`, `src/…` path the README references
   exists; the demo/experiment entry points and their outputs exist;
   and every package in `library/` passes the platform's own static
   validator (the docs claim a valid library; the harness checks it).

## Judgement rules for stage 3

The scanner reports *candidates* (pattern matches with word-boundary
discipline); this harness judges them:

- `validate.py` and `VALIDATION.md` are excluded from the scan: they
  must name the gate they enforce (the scanner's path, the pattern
  families). That is a meta-reference, reviewed by hand — the same
  reason the upstream scanner lives outside the trees it scans.
- The literal strings inside the harness's own `judge()` (pattern
  names) are meta-references of the same kind.
- Astronomy-flavoured uses of the telescope term (a star at its
  highest point, etc.) in otherwise unrelated text are BENIGN; any
  candidate tied to an AI platform, product, employer path or
  internal repository name is REAL and blocks.
- Anything else matching is REAL until a human judges otherwise.

## What this harness does NOT verify

- Behaviour of the key-gated real-provider adapters (no keys in the
  harness environment; they are import-checked only).
- The React production build (run `npm run build` in `frontend/`;
  the harness checks the frontend *sources* and the scan covers
  them).
- Anything about a deployed Render instance — the harness validates
  the repository, not the deployment.
- Semantic quality of skill prose. Evals verify triggering and
  fixture-checked behaviour; whether instructions are *wise* is a
  review question, not a test.
