# SkillForge — experiment results

All numbers from actual runs of this code against the seeded
fixtures (`src/skillforge/corpus.py`), via
`experiments/run_experiments.py`. Offline tiers only.

## E1 — Trigger quality (whole-library regression)

80 trigger cases (40 examples that should fire, 40 near-miss
counter-examples that should not), each resolved against the
full 20-skill library: TP=40 FP=0 FN=0 TN=40;
precision 1.0, recall 1.0.

## E2 — Eval pass matrix (100 cases: trigger + task, per skill)

- stub-pro:   100/100 (1.0)
- stub-basic: 98/100 (0.98); failing: data-analysis/k1, verification-before-completion/k1

The basic tier's failures are its documented strategy property
(it rounds decimal operands before computing), surfacing in
exact-figure task cases — a measured capability difference,
not noise: trigger behaviour is identical across tiers.

## E3 — Approval gate

Demo task with publish approved: run status `completed`. With the approver denying publish:
`blocked_approval` (publish trace: ['denied']). The analysis completes; the
publish does not happen.

## E4 — Dynamic creation (Phase 1 flow)

Created `unit-economics-snapshot` from a description + one
demonstration: ok=True, registered as `shadow`,
trial 3/3 passed, flow took 0.69s.
As shadow, a matching task resolved with primary=None and shadow_hits=['unit-economics-snapshot'] —
seen, logged, not governing. After promotion to active, the
same task ran under it (primary=unit-economics-snapshot, status
completed) and its output carried the verified
per-unit figures (True).

## E5 — Vanilla import

A SKILL.md-only folder imported with synthesised safe
defaults: lifecycle `imported`, static validation
valid=True with 1 warning(s).
Permission summary at import:

- Tools: none
- Scripts it may run: none
- Network: none
- Files it may write: sandbox only
- Needs human approval for: nothing

## Honest limits

- The offline tiers execute a step's procedure *structure*
  (tools, sections, gates); following skill prose
  *semantically* is what a keyed model does through the
  same seam — unmeasured here because it needs keys.
- Trigger quality is measured against the library's own
  authored cases (positives + authored near-misses), not
  an external benchmark.
