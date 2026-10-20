---
name: test-driven-development
description: 'Drive implementation with tests: write the failing test first, watch it fail for the right
  reason, implement the minimum change, keep the suite green, then refactor. Use when building or fixing
  behaviour in code.'
---

# test-driven-development

## Purpose

Drive implementation with tests, in the order that makes tests mean
something: red, green, refactor.

## Procedure

1. **Write the failing test first.** It names the behaviour, uses the
   real code path, and asserts the observable outcome — not the
   implementation detail.
2. **Watch it fail for the right reason.** A test that fails because of a
   typo in the test proves nothing. The failure message must be the bug,
   stated plainly.
3. **Implement the minimum change** that makes the test pass. Not the
   elegant change — the minimum one. Elegance is step 5.
4. **Run the whole suite.** The new test green and nothing else red; a
   fix that breaks a neighbour is a trade, and trades are decided
   consciously.
5. **Refactor with the suite as the safety net.** Now improve the shape;
   the tests arbitrate whether behaviour moved.

## Rules

- No production code without a failing test that demanded it.
- If you cannot write the test, you do not understand the behaviour yet —
  go back to the requirements.
