
"""Custom deterministic verifier: the artifact must carry the
recomputed net-revenue figure and a Verification section."""
def verify(case, artifact, ctx):
    totals = ctx["totals"]
    expect = f"{totals['net_revenue']:.2f}"
    if "## Verification" not in artifact:
        return False, "no Verification section"
    if expect not in artifact:
        return False, f"net revenue {expect} not present in artifact"
    return True, "verification figure present and recomputed"
