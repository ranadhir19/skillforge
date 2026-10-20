---
name: postgres-best-practices
description: 'Review Postgres schemas and queries for the classic production problems: unindexed foreign
  keys, sequential scans, unconstrained text states, unsafe migrations. Use for schema reviews and query
  tuning.'
---

# postgres-best-practices

## Purpose

Review Postgres schemas and queries for the problems that only hurt at
production scale — while they are still cheap to fix.

## The checks, in order

1. **Foreign keys without indexes.** Postgres does not index the
   referencing side automatically; joins and cascading deletes degrade
   to sequential scans. Every FK column gets an index or a written
   reason why not.
2. **Free-text state columns.** A status as unconstrained TEXT invites
   'Shipped', 'shipped' and 'SHIPPED ' to coexist. Use a check
   constraint or an enum.
3. **Missing timestamps and audit columns.** created_at / updated_at
   are nearly free at creation and nearly impossible to retrofit.
4. **Sequential scans on hot paths.** Ask for the query plan of the top
   queries; a seq scan on a growing table is a scheduled outage.
5. **Unsafe migrations.** Adding a non-null column without a default on
   a large table, or an index without CONCURRENTLY, locks writes.
   Migrations are reviewed as production changes, not paperwork.
6. **Types that lie.** Money as float, ids as text, booleans as
   integers — each is a bug farm.

## Output

Findings ordered by impact, each with the recommended change and the
migration note (locking behaviour, backfill need, rollback shape).
