---
name: verification-before-completion
description: 'Before claiming any work is done, verify the actual result and show the evidence: recompute
  key numbers from their sources, run the checks, compare against expectations. Use before reporting completion
  of an analysis, fix or build.'
---

# verification-before-completion

## Purpose

Before claiming any work is done, verify the actual result and show the
evidence. A claim without a check that was run *after* the work is a guess
wearing a uniform.

## Procedure

1. **State the claim precisely.** "Net revenue is X" — not "the analysis
   looks right."
2. **Recompute from source.** Every load-bearing number is recomputed from
   its source rows with a tool, independently of how it was first produced.
   Never verify a number against the document that asserts it.
3. **Run the checks.** The suite, the assertion, the query — actually run
   it, on the final artifact, after the last edit.
4. **Compare and report discrepancies.** Expected vs actual, side by side.
   A discrepancy is reported, not rounded away.
5. **Report with provenance.** Say what was checked, how, and what the
   evidence was. "Verified" without the method is not verification.

## Rules

- Evidence beats confidence; a rerun beats a recollection.
- If a check cannot be run, the claim is downgraded to unverified —
  say so in the output, in the Verification section.
- Never strengthen the claim beyond what the evidence covers.
