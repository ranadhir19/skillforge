
"""Cross-check: the script's aggregate over the CSV asset must equal
the platform metrics table's total for the same column."""
import re

def verify(case, artifact, ctx):
    m = re.search(r"sum\(revenue_usd\) = ([0-9.]+)", artifact)
    if not m:
        return False, "script aggregate line not found in artifact"
    got = float(m.group(1))
    want = float(ctx["totals"]["revenue_all"])
    if abs(got - want) > 0.005:
        return False, f"CSV aggregate {got} != metrics total {want}"
    return True, "CSV aggregate cross-checks against the metrics table"
