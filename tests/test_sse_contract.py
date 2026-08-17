"""The wire contract between the agent runtime and the Next.js frontend.

This is the keystone characterization test of the SEPHIROTH architecture
migration. The frontend hand-rolls its SSE parsing in
`platform/frontend/app/copilot/page.tsx:262-341`: it splits the byte stream on
blank lines, requires each chunk to start with `data: `, `JSON.parse`s the
remainder, and switches on `event.event`. Nothing validates the shape at
runtime, so a drift in field names or casing degrades the UI silently.

Five event types are frozen (see `docs/00-migration-charter.md` §2):
`routing`, `agent_completed`, `final`, `persisted`, `error`.

The frontend silently ignores unknown events, so *adding* an event type is
backward-compatible. Changing these five is not.

This module is never deleted — it outlives the migration and remains the
permanent contract test. Passing unmodified against the Phase 3 executor is
part of that phase's parity proof (AC-003-02, docs/specs/SPEC-003-agent-runtime.md).

Phase 4 (SPEC-004) added two additive, optional keys to `final` —
`verification_report` and `abstention` — the frontend ignores unknown keys,
so `test_final_event_shape`'s exact-set assertion below was extended to
include them; no existing key/casing changed. Verifies AC-004-08
(docs/specs/SPEC-004-verification-safety.md).

Phase 5 (SPEC-006) added one more additive key, `trace` (a persisted,
replayable `ExecutionTrace` — see docs/specs/SPEC-006-telemetry.md) — same
additive-only pattern, `test_final_event_shape` extended again. Verifies
AC-006-07.
"""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import sephiroth.models.factory as factory_module
from api.routers import agents as agents_router_module
from auth import router as auth_router_module
from core.db import get_session
from sephiroth.runtime import stream_consultation
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.contract

CREDS = {"email": "sse@example.org", "name": "Dr. Wire", "password": "password123"}

# A long answer so the 280-char `summary` truncation is exercised for real.
LONG_ANSWER = "Metformin remains first-line therapy. " * 40

EVIDENCE_SCRIPT = [
    ("tool", "search_clinical_guidelines", {"query": "type 2 diabetes first line"}),
    ("answer", LONG_ANSWER),
]
COORDINATOR_SCRIPT = [
    ("answer", "Summary: metformin is first-line [ADA Standards of Care in Diabetes, 2024]."),
]
SCRIPTS = {
    "clinical evidence specialist": EVIDENCE_SCRIPT,
    "coordinating physician-assistant": COORDINATOR_SCRIPT,
}


# --------------------------------------------------------------------------
# Workflow-level: event shapes, without HTTP/auth/DB in the way
# --------------------------------------------------------------------------


async def _workflow_events(context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    client = FakeLLMClient(scripts=SCRIPTS, default_script=[("answer", "specialist output")])
    return [e async for e in stream_consultation(client, "first-line therapy?", context=context)]


async def test_event_order_is_routing_then_completions_then_final():
    events = await _workflow_events()
    kinds = [e["event"] for e in events]

    assert kinds[0] == "routing", f"stream must open with `routing`, got {kinds[0]!r}"
    assert kinds[-1] == "final", f"stream must close with `final`, got {kinds[-1]!r}"
    assert set(kinds[1:-1]) == {"agent_completed"}, (
        f"only `agent_completed` may appear between routing and final, got {kinds}"
    )


async def test_routing_agents_use_underscore_node_names():
    """`routing` carries *node* names. The frontend maps them with
    `.replace("_", "-")` to match the agent chips, so the underscore form is
    load-bearing."""
    events = await _workflow_events({"medications": ["warfarin", "aspirin"]})
    routing = events[0]

    assert set(routing.keys()) == {"event", "agents"}
    assert "drug_safety" in routing["agents"], (
        "node name must stay in underscore form — the frontend un-escapes it"
    )
    assert "drug-safety" not in routing["agents"]


async def test_agent_completed_shape_and_hyphenated_identity():
    """`agent_completed.agent` is the *display* name (hyphenated), which is the
    opposite convention to `routing`. Both are relied on by the frontend's
    dual match: `p.name === event.agent || p.name.replace("-","_") === event.agent`."""
    events = await _workflow_events({"medications": ["warfarin"]})
    completed = [e for e in events if e["event"] == "agent_completed"]

    assert completed, "at least one agent_completed expected"
    for event in completed:
        assert set(event.keys()) == {"event", "agent", "summary", "tool_calls"}, (
            f"agent_completed field set drifted: {sorted(event.keys())}"
        )
        assert isinstance(event["summary"], str)

    names = {e["agent"] for e in completed}
    assert "drug-safety" in names, "display name must be hyphenated here"
    assert "drug_safety" not in names


async def test_agent_completed_tool_calls_omit_result():
    """`agent_completed` deliberately strips `result` to keep the stream small;
    `final` carries it because citation auditing needs it."""
    events = await _workflow_events()
    completed = [e for e in events if e["event"] == "agent_completed"]
    tool_calls = [c for e in completed for c in e["tool_calls"]]

    assert tool_calls, "the evidence script performs a tool call"
    for call in tool_calls:
        assert set(call.keys()) == {"name", "arguments"}, (
            f"agent_completed tool_calls must be {{name, arguments}}, got {sorted(call.keys())}"
        )
        assert "result" not in call


async def test_agent_completed_summary_truncated_at_280_chars():
    events = await _workflow_events()
    completed = [e for e in events if e["event"] == "agent_completed"]
    summaries = [e["summary"] for e in completed if e["summary"]]

    assert summaries, "expected a non-empty summary"
    assert any(len(s) == 280 for s in summaries), (
        f"expected a summary truncated to exactly 280 chars, got lengths {[len(s) for s in summaries]}"
    )
    assert all(len(s) <= 280 for s in summaries)


async def test_final_event_shape():
    events = await _workflow_events()
    final = events[-1]

    assert set(final.keys()) == {
        "event",
        "answer",
        "agents_involved",
        "tool_calls",
        "citation_report",
        "explanation",
        "verification_report",
        "abstention",
        "trace",
    }, f"final field set drifted: {sorted(final.keys())}"
    assert isinstance(final["answer"], str) and final["answer"]
    assert final["agents_involved"] == sorted(final["agents_involved"]), (
        "agents_involved must be sorted — it is persisted and rendered in order"
    )


async def test_final_tool_calls_retain_result():
    """`citation_guard.audit()` harvests allowed citations from tool *results*.
    Dropping `result` here silently makes every real citation look fabricated."""
    events = await _workflow_events()
    tool_calls = events[-1]["tool_calls"]

    assert tool_calls, "expected tool calls in the final event"
    for call in tool_calls:
        assert "result" in call, "final tool_calls must retain `result` for citation auditing"
        assert "agent" in call, "final tool_calls are tagged with their originating agent"


async def test_citation_report_keys_are_frozen():
    """These three keys are persisted to `consultations.citation_report` and
    read by the frontend's Citation Guard panel."""
    events = await _workflow_events()
    report = events[-1]["citation_report"]

    assert set(report.keys()) == {"verified", "fabricated", "total_checked"}, (
        f"citation_report keys drifted: {sorted(report.keys())}"
    )
    assert isinstance(report["verified"], list)
    assert isinstance(report["fabricated"], list)
    assert isinstance(report["total_checked"], int)


async def test_every_event_is_json_serializable():
    """The router serializes with `json.dumps(event, default=str)`; a
    non-serializable value would become a stringified repr and reach the
    frontend as garbage rather than failing loudly."""
    events = await _workflow_events({"medications": ["warfarin"], "lab_results": {"a1c": 7.4}})
    for event in events:
        json.dumps(event)  # no default= — must be natively serializable


# --------------------------------------------------------------------------
# Endpoint-level: wire framing and the `persisted` event
# --------------------------------------------------------------------------


@pytest.fixture
def app(db_session, monkeypatch):
    """Mount the routers by hand (the established convention in this suite) and
    swap both the LLM singleton and the streaming endpoint's session factory."""
    monkeypatch.setattr(
        factory_module,
        "_client",
        FakeLLMClient(scripts=SCRIPTS, default_script=[("answer", "specialist output")]),
    )

    # `/consult/stream` persists via `SessionLocal()` directly rather than the
    # injectable dependency, because the response is already streaming by then.
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(agents_router_module, "SessionLocal", lambda: _session_cm())

    application = FastAPI()
    application.include_router(auth_router_module.router, prefix="/api/auth")
    application.include_router(agents_router_module.router, prefix="/api/agents")

    async def override_session():
        yield db_session

    application.dependency_overrides[get_session] = override_session
    return application


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _token(client: AsyncClient) -> str:
    res = await client.post("/api/auth/register", json=CREDS)
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def _parse_sse(raw: str) -> List[Dict[str, Any]]:
    """Parse exactly the way the frontend does: split on blank lines, require
    the `data: ` prefix, JSON-parse the remainder."""
    events = []
    for chunk in raw.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        assert chunk.startswith("data: "), f"SSE frame missing `data: ` prefix: {chunk[:60]!r}"
        events.append(json.loads(chunk[6:]))
    return events


async def test_stream_wire_framing_and_persisted_event(client):
    async with client:
        token = await _token(client)
        res = await client.post(
            "/api/agents/consult/stream",
            json={"query": "first-line therapy for type 2 diabetes?", "context": {}},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert res.headers["cache-control"] == "no-cache"
        assert res.headers["x-accel-buffering"] == "no"

        events = _parse_sse(res.text)
        kinds = [e["event"] for e in events]

        assert kinds[0] == "routing"
        assert kinds[-1] == "persisted", "the stream must end by handing back the consultation id"
        assert "final" in kinds
        assert kinds.index("final") == len(kinds) - 2, "`final` immediately precedes `persisted`"

        persisted = events[-1]
        assert set(persisted.keys()) == {"event", "id"}
        assert persisted["id"], "persisted.id enables Export PDF without a reload"


async def test_stream_requires_auth(client):
    async with client:
        res = await client.post("/api/agents/consult/stream", json={"query": "anything at all"})
        assert res.status_code == 401


async def test_streamed_final_matches_persisted_history(client):
    """`explanation` is rebuilt on read rather than persisted. This asserts the
    live and rebuilt views agree, which is what keeps history and PDF export
    consistent with what the user just saw."""
    async with client:
        token = await _token(client)
        auth = {"Authorization": f"Bearer {token}"}

        res = await client.post(
            "/api/agents/consult/stream",
            json={"query": "first-line therapy for type 2 diabetes?", "context": {}},
            headers=auth,
        )
        events = _parse_sse(res.text)
        final = next(e for e in events if e["event"] == "final")

        history = (await client.get("/api/agents/history", headers=auth)).json()
        assert len(history) == 1
        row = history[0]

        assert row["answer"] == final["answer"]
        assert row["agents_involved"] == final["agents_involved"]
        assert row["citation_report"] == final["citation_report"]
        assert row["explanation"] == final["explanation"], (
            "the rebuilt explanation diverged from the streamed one — history and "
            "PDF export would show something different from the live consultation"
        )
