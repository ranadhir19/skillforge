#!/usr/bin/env python3
"""Aggregate one column of a CSV asset (sum/avg/max/min/count).

Input: JSON on stdin {"asset": "q1_metrics.csv", "column": "revenue_usd",
"op": "sum", "where": {"region": "North"} (optional exact-match filter)}.
Output: one line "op(column) = value" with two decimals (count: integer).
"""
import csv
import json
import os
import sys


def main():
    spec = json.load(sys.stdin)
    skill_dir = os.environ["SKILLFORGE_SKILL_DIR"]
    path = os.path.join(skill_dir, "assets", spec["asset"])
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    where = spec.get("where") or {}
    rows = [r for r in rows
            if all(r.get(k) == v for k, v in where.items())]
    col = spec["column"]
    op = spec.get("op", "sum")
    if op == "count":
        print(f"count({col}) = {len(rows)}")
        return
    vals = [float(r[col]) for r in rows]
    value = {"sum": sum(vals), "avg": sum(vals) / len(vals),
             "max": max(vals), "min": min(vals)}[op]
    print(f"{op}({col}) = {value:.2f}")


if __name__ == "__main__":
    main()
