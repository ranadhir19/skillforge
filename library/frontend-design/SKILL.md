---
name: frontend-design
description: 'Design a frontend screen or flow before building it: layout, component inventory, all states
  (loading, empty, error, success), responsive behaviour and accessibility. Use for new screens and redesigns.'
---

# frontend-design

## Purpose

Design a frontend screen or flow before building it, so the build is a
translation exercise, not a design process conducted in code.

## Procedure

1. **Layout first.** The screen's job in one sentence; the primary
   action; where the eye goes first, second, third. If the layout
   needs a paragraph to explain, it is wrong.
2. **Component inventory.** Every component, its data, its owner. Reuse
   before invention: a new component is a maintenance commitment.
3. **All the states, not the happy one.** Loading, empty, error,
   partial, success, permission-denied. A design that only shows the
   success state will have the other states invented by users'
   confusion.
4. **Responsive behaviour.** What collapses, what stacks, what is
   hidden — decided per breakpoint, not "it wraps somehow".
5. **Accessibility as a section, not a hope.** Focus order, labels,
   contrast, keyboard path for the primary action.
6. **Open questions listed, not buried.** Anything undecided is named
   so it gets decided by a person, not by a deadline.

## Rules

- Design the error state with the same care as the success state.
- Every interactive element answers: what does it do, how do I know
  it worked?
