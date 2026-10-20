---
name: code-review
description: Review code or a diff for correctness, security and maintainability problems, ordered by
  severity, each finding tied to a location and a concrete fix. Use for pull requests, snippets and patches.
---

# code-review

## Purpose

Review code or a diff the way a careful senior engineer does: for the
bugs the author cannot see because they wrote it.

## Procedure

1. **Read for intent first.** What is this change trying to do? A review
   that misunderstands the intent produces noise, not findings.
2. **Hunt the classic failures.** Injection (string-built queries,
   unsanitised input), missing timeouts and retries on network calls,
   error paths that swallow failures, off-by-one and boundary handling,
   secrets in code, races on shared state.
3. **Order by severity.** Blockers (security, data loss, correctness)
   before maintainability before style. Label each finding with its
   severity and the concrete fix — "consider refactoring" is not a
   finding.
4. **Tie every finding to a location.** File, function, line where
   possible. A finding nobody can find again is an opinion.
5. **Separate nits.** Style and taste go in their own section, clearly
   optional. Never let a nit dilute a blocker.

## Rules

- Review the code, not the author.
- If the change needs a test that is not there, that is a finding.
- Approve only what you would defend in the incident review.
