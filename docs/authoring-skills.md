# How to author a skill

A skill is a folder. This guide takes you from an idea to a package
that validates, triggers precisely, and passes its own evals. The
twenty packages under `library/` are worked examples — read
`library/data-analysis/` for a full one and
`library/pdf-extract-and-fill/` for a script-bearing one.

## 1. Start from a recurring task

Good skills come from tasks done repeatedly, with a recognisable
shape and a checkable result. If you cannot state how you would know
the skill worked, you are not ready to write it — write the eval
first (step 5) and let it tell you.

## 2. Write SKILL.md

Frontmatter carries exactly two load-bearing fields:

```markdown
---
name: my-skill            # kebab-case, must equal the folder name
description: <the trigger>
---

# my-skill

## Purpose
## When to use
## Procedure
## Rules
```

- **The description is the trigger.** Write it as the condition under
  which the skill should fire, in the vocabulary users actually use:
  "Diagnose a bug or production incident with a disciplined loop… Use
  for failures, outages, wrong results." A summary of the procedure
  is a bad trigger.
- **Keep the body lean** (guidance: under ~5000 tokens). The body is
  loaded whenever the skill governs a step; bulk belongs in
  `references/`, loaded on demand.
- **Write procedures, not vibes.** Numbered steps, decision rules,
  and the output contract. "Be careful" is not a step.

## 3. Write the manifest (skill.yaml)

```yaml
apiVersion: skillforge/v1
name: my-skill
version: 0.1.0
lifecycle: draft
triggers:
  examples: ["a task that should fire it", "another phrasing"]
  counter_examples: ["the nearest miss that should NOT fire it"]
requires:
  tools: ["native:doc_search"]
  capabilities: ["tool_calling"]     # never model names
permissions:
  tools: ["native:doc_search"]
  scripts: []                        # every script on disk must be listed
  network: none                      # none | allowlist | any
  filesystem: { read: [], write: [""] }
  approval_required_for: []          # e.g. [publish]
composition: { composes: [], conflicts: [] }
governs: [research, write]           # step actions this skill governs
output: { sections: ["Findings", "Fix"] }
budget: { max_tokens_per_run: 30000, max_script_seconds: null }
evals: { suite: evals/cases.yaml, holdout: null, min_pass: 0.9 }
```

Principles:

- **Least privilege by default.** Grant only the tools the procedure
  uses. A step whose action needs a tool the skill does not grant is
  refused at runtime — that refusal is a feature; design for it.
- **Counter-examples are mandatory in spirit.** Precision is
  untestable without near-misses. Pick the task most likely to be
  confused with yours (usually a sibling skill's home turf).
- **Capabilities, not models.** `requires.capabilities` names what
  the skill needs (tool_calling, long_context, vision,
  code_execution). The resolver checks the *bound provider*, so the
  same package runs anywhere that can honour it — and is excluded,
  with the reason surfaced, anywhere that cannot.
- **Scripts are code you ship.** They run sandboxed (run directory as
  cwd, scrubbed environment, timeout from your budget) and only if
  listed in `permissions.scripts`. A script on disk that is not
  listed fails static validation — deliberately.

## 4. Structure the output

Declare `output.sections`. A governed write step produces a
deliverable with exactly those sections; your evals (and your users)
can then check structure deterministically.

## 5. Write the evals (evals/cases.yaml)

Two case kinds:

```yaml
cases:
  - id: t1
    kind: trigger
    task: "a task that should fire it"
    should_fire: true
  - id: t3
    kind: trigger
    task: "the near-miss"
    should_fire: false
  - id: k1
    kind: task
    task:
      goal: "..."
      sub_questions: ["..."]       # research over the fixtures
      lookups: [{label: "total revenue", metric: "revenue_usd"}]
      computations: [{label: "net revenue",
                      expression: "{total revenue} - {total costs}",
                      refs: true}]
      title: "..."
    expect:
      sections: ["Findings", "Fix"]
      contains_all: ["{corpus:revenue_all}"]   # fixture placeholders
      contains_none: []
      regex: []
      min_chars: 300
```

- Trigger cases run against the **whole library**: your example must
  fire your skill with all 19 others present, and your counter-example
  must not. That is trigger regression by construction.
- Task cases verify the artifact with deterministic assertions
  against the platform fixtures (`{corpus:<key>}` placeholders resolve
  to computed totals). For checks assertions cannot express, ship
  `evals/verifiers.py` with `verify(case, artifact, ctx) -> (bool,
  detail)` — spreadsheet-analysis uses one to cross-check its script
  aggregate against the metrics table.
- Mark independently-authored cases `holdout: true`; they are
  reported separately, always. (The rule that matters: whoever writes
  the exam, it must not be the candidate being examined.)

## 6. Validate, evaluate, promote

```bash
python3 -c "from skillforge import validate_package; \
print(validate_package('library/my-skill'))"     # static contract
python3 -m pytest tests/test_library.py          # behaviour, whole library
```

Lifecycle discipline: `draft` while authoring → `shadow` when it
should be observed (the resolver scores and logs it; it does not
govern) → `active` when its suite passes and a human promotes it →
`deprecated` when superseded. Every transition is written to the
audit chain. A skill edited by hand around these gates is exactly
what the platform exists to prevent.

## 7. Or let the platform draft it

Describe the capability and demonstrate it once (the task, its steps,
its input/output). The creation flow drafts the package with
least-privilege defaults, validates it, trials it against starter
evals derived from your demonstration, and stops at the approval
gate. You approve the plain-language permission summary — not the
YAML. See the Create screen in the demo UI, or `skillforge.creator`.
