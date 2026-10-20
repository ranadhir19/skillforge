---
name: webapp-testing
description: 'Plan and structure testing for a web application change: derive test cases from the acceptance
  criteria, cover the unhappy paths, and report results as evidence, not vibes. Use before shipping a
  UI or flow change.'
---

# webapp-testing

## Purpose

Plan and structure testing for a web application change so "it works" is
a claim with evidence attached.

## Procedure

1. **Derive cases from acceptance criteria**, one case per criterion,
   stated as: given / when / then. Criteria without cases are wishes.
2. **Cover the unhappy paths deliberately:** empty states, invalid
   input, expired sessions, slow and failed requests, double-submits,
   the back button. Production incidents live here; the checkout
   outage in the corpus was a session-state failure, not a happy-path
   failure.
3. **Include regression cases for what previously broke** in this area —
   the incident history is a test-plan input, not trivia.
4. **Define evidence per case:** screenshot, log line, or assertion —
   named before the run. "Checked it" is not evidence.
5. **Report results against the plan:** pass/fail per case, evidence
   attached, untested areas listed as untested.

## Rules

- The happy path is the smallest part of the plan.
- A test plan written after testing is fiction; write it first.
