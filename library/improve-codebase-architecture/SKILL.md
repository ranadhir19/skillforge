---
name: improve-codebase-architecture
description: 'Find structural improvement opportunities in a codebase: hotspots, god modules, circular
  dependencies and boundary leaks, each with a sized, reversible proposal. Use for architecture reviews
  and refactoring plans.'
---

# improve-codebase-architecture

## Purpose

Find where a codebase's structure is taxing every change, and propose
improvements sized to be reversible. Architecture work that cannot be
undone gets proposed very carefully or not at all.

## Procedure

1. **Measure hotspots, don't vibe them.** Fan-in/fan-out, module size,
   change frequency, dependency cycles, boundary crossings (code
   reaching past a facade into internals).
2. **Price the pain.** Each hotspot gets its cost stated concretely:
   what change is slow, risky or surprising because of it.
3. **Propose the smallest structural move** that removes the measured
   pain: extract a facade, break a cycle with an interface, split a god
   module along its change axes.
4. **Sequence for reversibility.** Order proposals so each lands
   independently and can be reverted independently. Big-bang rewrites
   are refused as proposals.
5. **Name the risks.** What the new structure makes harder, and the
   evidence you would watch to know the move failed.

## Rules

- No proposal without a measurement behind it.
- "Cleaner" is not a benefit; "checkout changes stop touching 14
  modules" is.
- Respect working ugly code over elegant unproven code.
