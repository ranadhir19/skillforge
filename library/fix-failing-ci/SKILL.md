---
name: fix-failing-ci
description: 'Get a failing CI pipeline green: find the first real failure (not the cascade), classify
  it (code, test, environment, flake), apply the minimal fix, and state what would prove it. Use when
  a build goes red.'
---

# fix-failing-ci

## Purpose

Get a failing pipeline green by fixing the *cause*, in the order the
evidence demands — not by re-running until it passes.

## Procedure

1. **Find the first real failure.** Pipelines fail in cascades; later
   failures are usually downstream noise. The first failing job, its
   first failing test, its assertion — that is the case.
2. **Classify before fixing.** Code defect, test defect, environment
   (including rounding/ordering/timezone nondeterminism), or flake.
   Each class has a different correct fix; applying the code-fix to an
   environment problem teaches the pipeline to lie.
3. **Minimal fix.** Change the smallest thing that addresses the class.
   If the fix is "increase the timeout", say what evidence shows the
   timeout is the cause.
4. **State the proof.** Which job, run green, how many times — before
   declaring the pipeline fixed. One green run after a flake proves
   nothing; say how you distinguished.
5. **Skipped jobs are part of the report.** What never ran because of
   the failure, and when it will.

## Rules

- Never fix the second failure first.
- A re-run is a diagnostic, not a remedy.
- If it is a flake, the fix is a quarantine and a ticket, not a shrug.
