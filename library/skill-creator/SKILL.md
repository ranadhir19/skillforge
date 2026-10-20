---
name: skill-creator
description: 'Create a new skill package from a description or a demonstration: draft the SKILL.md and
  manifest, generate starter evals, and take the package through validation, trial and the approval gate.
  Use when a recurring task should become a reusable skill.'
---

# skill-creator

## Purpose

Create a new skill package from a description or a demonstration: draft the
SKILL.md and manifest, generate starter evals, and take the package through
validation, trial and the approval gate.

## When to use

When someone has done a task twice and will do it a third time — or asks for
a capability the library does not have. Do NOT use it to perform the task
itself; performing is the created skill's job.

## Procedure

1. **Interview or infer.** From the description (or the demonstration: one
   real task, its input, its output), establish: the trigger (what tasks
   should fire it), one near-miss that should NOT fire it, the tools and
   files it genuinely needs, and the output shape.
2. **Draft the package.** SKILL.md: frontmatter name (kebab-case) and a
   description written as a trigger, not a summary. Body: purpose, when to
   use, a numbered procedure, the output contract. Keep the body lean;
   push bulk into references/.
3. **Write the manifest.** Least privilege by default: no scripts, no
   network, sandbox-only writes. Declare trigger examples AND
   counter-examples — precision is untestable without near-misses.
   Declare required capabilities, never model names.
4. **Generate starter evals from the demonstration.** One positive trigger,
   one counter-example trigger, one task case whose expectations are facts
   from the demonstration's output. Label them starter evals: the author
   of the exam is the platform's fixture set, not the candidate.
5. **Validate statically.** Name/dir/manifest sync, referenced files
   exist, every script on disk is declared in permissions.scripts.
6. **Trial in a sandbox.** Run the suite against an isolated library.
   Below the package's pass bar, it does not reach the gate.
7. **Approval gate.** Show a human the plain-language permission summary,
   the validation report and the trial scores. Approval registers the
   skill as *shadow*; promotion to active is a separate decision.

## Output

A package folder plus a creation report: validation result, trial pass
rate, permission summary, and the lifecycle state it registered in.
