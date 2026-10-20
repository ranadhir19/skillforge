---
name: deploy-checklist
description: 'Run a deployment as a checklist, not a memory test: pre-flight checks, the deploy steps,
  smoke tests with named evidence, and a rehearsed rollback. Use for releases and config pushes, especially
  cache and configuration changes.'
---

# deploy-checklist

## Purpose

Run a deployment as a checklist, not a memory test. The payments outage
in this platform's corpus was a config push that changed a cache TTL
without an invalidation step — exactly the class of failure a checklist
exists to prevent.

## Procedure

1. **Pre-flight.** The change is reviewed by a second person; the diff
   is small enough to describe in one sentence; the rollback is
   identified *before* the deploy, not during the incident. Config
   changes that alter caching declare their invalidation step here —
   no step named, no deploy.
2. **Deploy steps.** Ordered, each with its verification. One change at
   a time; a release that bundles three changes has no diagnosis path
   when it fails.
3. **Smoke tests with named evidence.** The three user-visible behaviours
   that prove the deploy lived: named checks, named expected results,
   checked against the real system.
4. **Rollback.** The exact commands or clicks, the state they restore,
   and the decision deadline: if smoke is not green by T+15 minutes,
   rollback is the default, not a debate.
5. **Publish through the gate.** The checklist itself is published only
   with human approval.

## Rules

- Friday-evening deploys need a stronger reason than weekday ones.
- "We tested in staging" is pre-flight evidence only if staging matches
  production in the dimension being changed.
