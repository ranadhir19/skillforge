"""The seeded world the demo, evals and experiments run against.

Entirely fictional and deterministic: a small document corpus (policy
notes, an incident postmortem, a CI log, a code snippet, a schema, a
merge conflict, an architecture note, handbook pages, a filled form)
and a Q1 metrics table. The starter library's eval cases verify
against *these* fixtures with deterministic verifiers — that is what
"the skill worked" means in the offline tier, and the fixtures are
labelled as fixtures everywhere they surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tools import Chunk

CHUNKS = [
    Chunk("c-policy", "Refund policy",
          "Helios refund policy: customers may request a full refund "
          "within 30 days of purchase. Unused subscription credits "
          "never expire. Refunds are issued to the original payment "
          "method within 5 business days."),
    Chunk("c-incident", "Payments outage postmortem, 2026-03-14",
          "Incident INC-2041: on 2026-03-14 checkout success fell to "
          "61 percent for 47 minutes. Root cause: a configuration push "
          "at 14:02 UTC raised the session-cache TTL from 300 seconds "
          "to 86400 seconds without invalidating existing entries, so "
          "stale session rows pinned expired payment tokens. Resolution: "
          "the cache was flushed and the TTL reverted to 300 seconds. "
          "Action items: config pushes that change cache TTL require a "
          "cache-invalidation step and a second approver."),
    Chunk("c-ci", "CI run 8812 log excerpt",
          "CI run 8812. Jobs: unit-tests PASS (412 tests). lint PASS. "
          "integration-tests FAIL: first failure "
          "test_checkout_totals: AssertionError: expected total "
          "210505.25 but got 210505.26. The totals aggregation sums "
          "floats in row order; the failure is a one-cent rounding "
          "drift in the aggregation, not a data error. package-tests "
          "were skipped after the failure."),
    Chunk("c-diff", "Code snippet under review: user lookup helper",
          "def get_user(conn, user_id):\n"
          "    q = \"SELECT * FROM users WHERE id = \" + user_id\n"
          "    return conn.execute(q).fetchone()\n\n"
          "def fetch(url):\n"
          "    return requests.get(url).json()\n"
          "Issues a reviewer should catch: the query is built by "
          "string concatenation with an unescaped user_id (SQL "
          "injection), and requests.get is called without a timeout."),
    Chunk("c-schema", "Schema under review: orders service",
          "CREATE TABLE orders (id BIGSERIAL PRIMARY KEY, "
          "customer_id BIGINT REFERENCES customers(id), "
          "status TEXT, total NUMERIC(12,2), created_at TIMESTAMPTZ "
          "DEFAULT now()); CREATE TABLE order_items (order_id BIGINT "
          "REFERENCES orders(id), sku TEXT, qty INT); "
          "Review notes: customer_id and order_id are foreign keys "
          "with no index, so joins and cascades scan sequentially; "
          "status is free TEXT with no check constraint."),
    Chunk("c-conflict", "Merge conflict: retry configuration",
          "<<<<<<< HEAD\nmax_retries = 3  # protect the payments API "
          "from retry storms\n=======\nmax_retries = 5  # the vendor "
          "webhook endpoint is flaky; two extra retries cut missed "
          "deliveries\n>>>>>>> feature/webhook-retries\n"
          "Both intents are real: the payments API needs storm "
          "protection, and webhook delivery needs more attempts."),
    Chunk("c-arch", "Architecture hotspots scan",
          "Hotspot scan of the monorepo: the billing module is "
          "imported by 14 other modules (highest fan-in); utils is a "
          "4100-line god module; billing and reporting import each "
          "other (a circular dependency); the session cache is "
          "accessed directly from 9 modules instead of through the "
          "cache facade."),
    Chunk("c-handbook", "Remote work handbook, page 12",
          "Remote work: employees may work remotely up to 3 days per "
          "week. Core collaboration hours are 10:00 to 15:00 local "
          "time. Managers approve remote schedules one month ahead."),
    Chunk("c-handbook2", "Remote work handbook, page 13",
          "Remote work equipment: the company provides a laptop and a "
          "400 USD home-office stipend per year. Remote employees join "
          "the weekly all-hands by video. Travel to the office is "
          "reimbursed for quarterly planning weeks."),
    Chunk("c-form", "Filled form: vendor onboarding (text rendering)",
          "FORM vendor-onboarding\n"
          "applicant_name: Priya Nair\n"
          "vendor: Northwind Traders\n"
          "annual_spend_usd: 48200\n"
          "start_date: 2026-11-01\n"
          "approver: Marcus Lee\n"),
    Chunk("c-skill-anatomy", "Anatomy of a skill package",
          "A skill package is a folder: a SKILL.md holding frontmatter "
          "(name and description — the description is the trigger) and "
          "an instruction body under 5000 tokens; a manifest declaring "
          "triggers with counter-examples, tool permissions, budgets "
          "and an eval suite; optional scripts, references and assets "
          "loaded on demand. Packages carry provenance and a lifecycle "
          "state: draft, shadow, active, deprecated."),
    Chunk("c-metrics-note", "Metrics table notes",
          "The metrics table holds monthly regional figures for Q1 "
          "2026. revenue_usd is gross revenue in USD; costs_usd is "
          "platform cost; units is units sold. Net revenue is revenue "
          "minus costs."),
]

# region, month, revenue_usd, costs_usd, units
_ROWS = [
    ("North", "2026-01", 21000.00, 3600.00, 402),
    ("North", "2026-02", 21551.50, 3710.25, 415),
    ("North", "2026-03", 22000.00, 3800.00, 428),
    ("South", "2026-01", 18000.00, 3100.00, 360),
    ("South", "2026-02", 18420.75, 3150.50, 371),
    ("South", "2026-03", 17900.00, 3050.00, 358),
    ("East", "2026-01", 15200.00, 2600.00, 305),
    ("East", "2026-02", 15833.00, 2705.17, 318),
    ("East", "2026-03", 16100.00, 2750.00, 322),
    ("West", "2026-01", 14500.00, 2500.00, 290),
    ("West", "2026-02", 14900.50, 2562.50, 298),
    ("West", "2026-03", 15600.00, 2610.00, 307),
]

METRIC_ROWS = [{"region": r, "month": m, "revenue_usd": rev,
                "costs_usd": cost, "units": u}
               for r, m, rev, cost, u in _ROWS]


def _total(metric: str, region: str | None = None) -> float:
    return round(sum(r[metric] for r in METRIC_ROWS
                     if region is None or r["region"] == region), 2)


TOTALS = {
    "revenue_all": _total("revenue_usd"),
    "revenue_north": _total("revenue_usd", "North"),
    "costs_all": _total("costs_usd"),
    "units_all": int(_total("units")),
}
TOTALS["net_revenue"] = round(TOTALS["revenue_all"] - TOTALS["costs_all"], 2)


@dataclass
class TaskSpec:
    """A structured task: what the planner composes a workflow from."""
    task_id: str
    goal: str
    sub_questions: list = field(default_factory=list)     # research queries
    lookups: list = field(default_factory=list)           # data_lookup params
    computations: list = field(default_factory=list)      # {label, expression, refs}
    script_steps: list = field(default_factory=list)     # {skill, script, payload, label}
    title: str = "Deliverable"
    publish_to: str | None = None                         # sandbox filename
    skill_hint: str | None = None                         # pin a primary skill
    context_from: tuple = ()                              # step ids feeding write

    @property
    def text(self) -> str:
        return self.goal


def demo_task() -> TaskSpec:
    """The canonical demo task: Q1 revenue analysis, written up under
    the data-analysis skill and published to the sandbox."""
    return TaskSpec(
        task_id="demo-q1",
        goal="Analyse Q1 2026 revenue: total revenue, the North region "
             "total, total costs, units sold, and net revenue, then "
             "write up the findings.",
        sub_questions=["What does the metrics table contain and how is "
                       "net revenue defined?"],
        lookups=[
            {"label": "total revenue", "metric": "revenue_usd"},
            {"label": "north revenue", "metric": "revenue_usd", "region": "North"},
            {"label": "total costs", "metric": "costs_usd"},
            {"label": "units sold", "metric": "units"},
        ],
        computations=[
            {"label": "net revenue",
             "expression": "{total revenue} - {total costs}", "refs": True},
        ],
        title="Q1 2026 revenue analysis",
        publish_to="q1-revenue-analysis.md",
        skill_hint="data-analysis",
    )
