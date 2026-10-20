---
name: resolve-merge-conflict
description: "Resolve a merge conflict by reconstructing both sides' intent, preserving both where possible,\
  \ and flagging \u2014 never silently choosing \u2014 where the intents truly collide. Use when a merge\
  \ or rebase reports conflicts."
---

# resolve-merge-conflict

## Purpose

Resolve a merge conflict by understanding it. A conflict is two intents
that arrived at the same lines; deleting one side is a decision, and
decisions made silently are bugs with good timing.

## Procedure

1. **Reconstruct each side's intent.** Not just the diff — the *reason*:
   read the commit messages, the comments, the surrounding code. State
   each intent in one sentence a third engineer would accept.
2. **Classify the collision.** Independent intents (both can hold),
   overlapping intents (same goal, different means), or contradictory
   intents (cannot both hold).
3. **Resolve.** Independent: merge both, carefully. Overlapping: pick
   the means that serves the shared goal, and say why. Contradictory:
   do NOT choose — escalate with both intents stated and the trade-off
   priced.
4. **Verify the merge.** The result must parse, build, and pass the
   tests that touch the area. A conflict-free file that broke behaviour
   is not resolved.
5. **Record the decision.** Who decided, on what grounds — in the commit
   message, not in chat.

## Rules

- "Ours" and "theirs" are not arguments.
- When in doubt about intent, the escalation is the deliverable.
