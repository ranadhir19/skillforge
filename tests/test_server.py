"""Server tests: FastAPI + GraphQL surface over a real platform.

GraphQL behaviour is asserted through the actual HTTP layer
(TestClient), including a run mutation whose traces come back, and
the REST staged-creation gate (draft -> decide) that the UI uses.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("fastapi")
pytest.importorskip("strawberry")

from fastapi.testclient import TestClient  # noqa: E402

from skillforge import Platform  # noqa: E402
from server.app import create_app  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_ROOT = os.path.join(ROOT, "library")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("server")
    lib_copy = str(tmp / "library")
    shutil.copytree(LIB_ROOT, lib_copy)
    plat = Platform([lib_copy], str(tmp / "data"))
    return TestClient(create_app(plat))


def gql(client, query, variables=None):
    resp = client.post("/graphql", json={"query": query,
                                         "variables": variables or {}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "errors" not in body, body
    return body["data"]


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["skills"] == 20
    assert body["audit_chain_valid"] is True


def test_frontend_health_contract(client):
    """Pin the REST /health <-> UI header contract.

    Regression: App.jsx read health.auditChainValid (camelCase),
    but /health emits snake_case keys (audit_chain_valid) and the
    frontend's rest() helper passes the parsed JSON through with
    no case conversion -- so the value was always undefined and
    the header always rendered "audit chain BROKEN" even while
    the API reported a valid chain. (GraphQL fields ARE camelized
    by Strawberry -- schema.py's audit_chain_valid resolver is
    auditChainValid over GraphQL -- which is how the wrong
    convention got applied to the one REST read in the header.)
    """
    body = client.get("/health").json()
    assert body["audit_chain_valid"] is True
    app_jsx = open(os.path.join(ROOT, "frontend", "src", "App.jsx"),
                   encoding="utf-8").read()
    # The header must read the key /health actually emits...
    assert "health.audit_chain_valid" in app_jsx
    # ...and must not read the camelCase key REST never sends.
    assert "health.auditChainValid" not in app_jsx
    # The other two header fields must also match the payload.
    for key in ("status", "skills"):
        assert f"health.{key}" in app_jsx
        assert key in body


def test_graphql_library_browsing(client):
    data = gql(client, "{ skills { name lifecycle } }")
    names = sorted(s["name"] for s in data["skills"])
    assert len(names) == 20
    assert "data-analysis" in names
    one = gql(client, '{ skill(name: "data-analysis") { name tools network '
                      'approvalRequiredFor sections } }')
    skill = one["skill"]
    assert "native:calculator" in skill["tools"]
    assert skill["approvalRequiredFor"] == ["publish"]
    assert "Figures" in skill["sections"]


def test_graphql_skill_evals(client):
    data = gql(client, '{ skillEvals(name: "data-analysis") '
                       '{ total passed passRate } }')
    ev = data["skillEvals"]
    assert ev["total"] == 5 and ev["passed"] == 5 and ev["passRate"] == 1.0


def test_graphql_run_mutation(client):
    data = gql(client, """
        mutation { triggerRun(task: "What is our refund policy?",
                              provider: "stub-pro", autoApprove: true) {
            status primarySkill totalTokens
            traces { stepId action skill status } } }""")
    run = data["triggerRun"]
    assert run["status"] == "completed"
    assert run["totalTokens"] > 0
    assert any(t["stepId"] == "write" for t in run["traces"])


def test_rest_run_and_episodes(client):
    resp = client.post("/runs", json={
        "task": "Analyse Q1 revenue — totals, North region, costs and net",
        "provider": "stub-pro", "auto_approve": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["primary_skill"] == "data-analysis"
    eps = client.get("/episodes").json()
    assert eps and eps[-1]["provider"] == "stub-pro"


def test_rest_import_export(client, tmp_path):
    # export data-analysis (full), re-import under a fresh platform root
    resp = client.get("/export/data-analysis")
    assert resp.status_code == 200
    zip_path = tmp_path / "da.zip"
    zip_path.write_bytes(resp.content)
    export = client.get("/export/data-analysis", params={"portable": True})
    assert export.status_code == 200
    # importing a duplicate into the same library is refused
    with open(zip_path, "rb") as fh:
        resp = client.post("/import", files={"file": ("da.zip", fh)})
    assert resp.status_code == 400


def test_staged_creation_gate(client):
    demonstration = {
        "name": "margin-watch",
        "task": "Give me the margin watch for Q1",
        "steps": ["Look up revenue and costs.", "Compute the margin."],
        "sections": ["Totals", "Margin", "Notes"],
        "lookups": [1], "computations": [1],
        "task_spec": {
            "goal": "Margin watch for Q1 2026",
            "lookups": [{"label": "total revenue", "metric": "revenue_usd"},
                        {"label": "total costs", "metric": "costs_usd"}],
            "computations": [{"label": "margin",
                              "expression": "({total revenue} - {total costs}) / {total revenue}",
                              "refs": True}],
            "title": "Margin watch Q1"},
        "expect": {"sections": ["Totals", "Margin", "Notes"],
                   "contains_all": ["{corpus:revenue_all}"]},
    }
    resp = client.post("/skills/draft", json={
        "description": "Compute a margin watch for a quarter: revenue, "
                       "costs, and the margin ratio.",
        "demonstration": demonstration})
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["skill"] == "margin-watch"
    assert draft["trial"]["pass_rate"] == 1.0
    # not yet registered
    names = [s["name"] for s in gql(client, "{ skills { name } }")["skills"]]
    assert "margin-watch" not in names
    # human approves -> registered as shadow
    resp = client.post(f"/skills/{draft['draft_id']}/decide",
                       json={"approve": True, "lifecycle": "shadow"})
    assert resp.json()["registered"] is True
    names = [s["name"] for s in gql(client, "{ skills { name } }")["skills"]]
    assert "margin-watch" in names
    one = gql(client, '{ skill(name: "margin-watch") { lifecycle origin } }')
    assert one["skill"]["lifecycle"] == "shadow"
    assert one["skill"]["origin"] == "dynamic-creation"


def test_graphql_subscription_streams_traces(client):
    """The subscription resolver streams one event per executed step."""
    import asyncio

    from server.schema import schema

    async def collect():
        events = []
        result = await schema.subscribe(
            'subscription { runEvents(task: "What is our refund policy?") '
            '{ stepId status } }',
            context_value={"platform": client.app.state.platform,
                           "runs": {}})
        async for message in result:
            if message.errors:
                raise AssertionError(message.errors)
            events.append(message.data["runEvents"])
        return events

    events = asyncio.run(collect())
    assert events, "expected streamed trace events"
    assert all(e["status"] for e in events)
