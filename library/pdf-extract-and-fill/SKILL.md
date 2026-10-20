---
name: pdf-extract-and-fill
description: Extract structured fields from filled forms and documents, and fill form templates from structured
  data, verifying every value against the source. Use for onboarding forms, applications and document
  intake. Ships a sandboxed field-extraction script.
---

# pdf-extract-and-fill

## Purpose

Extract structured fields from filled forms and documents — and fill form
templates from structured data — with every value verified against its
source. (Authored original for this platform. The bundled script handles
text renderings of forms; a production deployment binds the same
procedure to a real document parser behind the tool seam.)

## Procedure

1. **Inventory the fields first.** List the fields the consumer needs
   before extracting anything. Extraction without a field list produces
   plausible-looking soup.
2. **Extract with the script, never by eyeballing.** The allowlisted
   script reads the source document and emits field = value lines.
   Values a human "reads off" a form are how wrong approvers and wrong
   amounts get into systems.
3. **Verify each value against the source.** Field, value, and where in
   the source it came from. MISSING is a first-class result — report it,
   never invent a plausible value.
4. **Flag ambiguity explicitly.** Two candidate values, a smudged field,
   a date in an unknown order: list them under Missing or ambiguous for
   a human, with both candidates shown.
5. **For filling:** write only values supplied in the structured input;
   a field with no supplied value stays blank and is reported.

## Rules

- Extracted data is evidence: keep the source next to the value.
- Never normalise silently (dates, amounts, names) — show the source
  form and the normalised form side by side when normalising is needed.
