---
name: diagnosing-bugs
description: 'Diagnose a bug or production incident with a disciplined loop: reproduce, minimise, form
  one hypothesis at a time, test it against evidence, fix the root cause, add a regression check. Use
  for failures, outages, wrong results.'
---

# diagnosing-bugs

## Purpose

Diagnose a bug or production incident with a disciplined loop. The
enemy is the plausible story adopted before the evidence arrives.

## Procedure

1. **Reproduce.** State the failure precisely: what, when, how often,
   who is affected. If you cannot reproduce it, your first job is the
   reproduction, not the fix.
2. **Gather evidence before theorising.** Logs, timelines, recent
   changes. Write down what is *known*, separately from what is
   *suspected*.
3. **One hypothesis at a time.** Each hypothesis must predict something
   checkable. Test the cheapest prediction first.
4. **Root cause, not first cause.** Keep asking "why" until the answer
   is a mechanism, not a person and not a coincidence.
5. **Fix the mechanism.** The smallest change that removes the cause.
6. **Regression check.** Name the test or monitor that would catch this
   class of failure next time, before the incident, not after.

## Rules

- Correlation in time is a clue, not a cause.
- Record rejected hypotheses — the next incident will thank you.
- If the evidence contradicts the favourite theory, the theory goes.
