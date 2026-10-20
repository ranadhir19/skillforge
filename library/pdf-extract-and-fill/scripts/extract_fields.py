#!/usr/bin/env python3
"""Extract named fields from a key: value form (text rendering).

Input: JSON on stdin {"asset": "vendor_form.txt", "fields": [...]}.
The form is read from this skill's assets/ directory (the platform
passes the package dir via SKILLFORGE_SKILL_DIR). Output: one
"field = value" line per requested field, or "field = MISSING".
"""
import json
import os
import sys


def main():
    spec = json.load(sys.stdin)
    skill_dir = os.environ["SKILLFORGE_SKILL_DIR"]
    path = os.path.join(skill_dir, "assets", spec["asset"])
    values = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if ":" in line:
                key, _, val = line.partition(":")
                values[key.strip()] = val.strip()
    for field in spec["fields"]:
        print(f"{field} = {values.get(field, 'MISSING')}")


if __name__ == "__main__":
    main()
