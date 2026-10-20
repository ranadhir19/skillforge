---
name: spreadsheet-analysis
description: 'Analyse spreadsheet data: profile the columns, compute aggregates with a sandboxed script
  (never mental arithmetic), cross-check totals against a second source, and explain anomalies. Use for
  CSV and metrics analysis and reconciliation.'
---

# spreadsheet-analysis

## Purpose

Analyse spreadsheet data so the numbers can be defended: profiled,
computed by script, and cross-checked against an independent source.

## Procedure

1. **Profile before computing.** Columns, types, row count, the grain
   (what one row means), and obvious gaps. Most spreadsheet errors are
   grain errors: monthly rows summed as if they were totals.
2. **Compute with the script.** Aggregates come from the allowlisted
   stats script over the file — never from mental arithmetic, never
   from reading a few rows and extrapolating.
3. **Cross-check against a second source.** The same total from the
   metrics table (or a stated control total). Two paths to one number
   is the cheapest audit there is; a mismatch is a finding, not an
   inconvenience.
4. **Explain anomalies.** Rows that break the pattern (a missing month,
   a sign flip, a 10x value) get named with their likely cause class:
   data entry, definition change, or real signal.
5. **Report with the grain stated.** Every figure carries its scope:
   which rows, which filter, which column definition.

## Rules

- A total without a cross-check is a draft number.
- Never average averages.
- Show the filter next to the figure, always.
