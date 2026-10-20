"""Quickstart: resolve, run, inspect — in a dozen lines.

    python3 examples/quickstart.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillforge import repo_platform

plat = repo_platform(os.path.join(os.path.dirname(__file__), ".."))

# A free-text task: the resolver picks the skills, the planner composes
# the workflow, the runtime executes it under their manifests.
bundle = plat.run_task("Research the remote work policy: days, core "
                       "hours, equipment")
res, rec = bundle["resolution"], bundle["record"]
print("active skills:", res.names(), "| primary:", res.primary)
print("status:", rec.status, "| tokens:", rec.total_tokens)
for line in res.log:
    print(" ", line)
print()
print(rec.final_output[:600])
