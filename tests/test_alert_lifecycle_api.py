"""`/api/alerts` — review/resolve lifecycle (SPEC-011)."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Alert, Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="alert-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Alert", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
async def alert_row(db_session):
    p = Patient(id="PAL1", name="Alert Patient", age=50, sex="M", medical_record_number="PT-PAL1")
    db_session.add(p)
    a = Alert(
        id="AL1",
        patient_id="PAL1",
        category="lab",
        severity="high",
        title="High potassium",
        detail="",
        source="risk_engine",
    )
    db_session.add(a)
    await db_session.commit()
    return a


async def test_resolve_without_review_is_rejected(client, alert_row):
    headers = await _clinician(client)
    res = await client.post("/api/alerts/AL1/resolve", headers=headers)
    assert res.status_code == 409


async def test_review_then_resolve(client, alert_row, db_session):
    headers = await _clinician(client)

    review_res = await client.post("/api/alerts/AL1/review", headers=headers)
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "reviewed"
    assert review_res.json()["reviewed_at"] is not None

    resolve_res = await client.post("/api/alerts/AL1/resolve", headers=headers)
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "resolved"
    assert resolve_res.json()["resolved_at"] is not None


async def test_resolve_cancels_active_escalation_workflow(client, alert_row, db_session):
    headers = await _clinician(client)
    workflow = Workflow(
        id="WFAL1", definition_key="alert_escalation", patient_id="PAL1", alert_id="AL1", status="active"
    )
    db_session.add(workflow)
    from datetime import datetime

    step = WorkflowStep(
        id="STAL1",
        workflow_id="WFAL1",
        step_key="escalate_check",
        step_type="alert_escalate_check",
        status="pending",
        due_at=datetime(2026, 12, 1),
        run_after=datetime(2026, 12, 1),
    )
    db_session.add(step)
    await db_session.commit()

    await client.post("/api/alerts/AL1/review", headers=headers)
    resolve_res = await client.post("/api/alerts/AL1/resolve", headers=headers)
    assert resolve_res.status_code == 200

    refreshed_wf = await db_session.get(Workflow, "WFAL1")
    refreshed_step = await db_session.get(WorkflowStep, "STAL1")
    assert refreshed_wf.status == "cancelled"
    assert refreshed_step.status == "cancelled"


async def test_list_alerts_filters_by_status(client, alert_row):
    headers = await _clinician(client)
    res = await client.get("/api/alerts", params={"status": "active"}, headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1

    res_empty = await client.get("/api/alerts", params={"status": "resolved"}, headers=headers)
    assert res_empty.json() == []
