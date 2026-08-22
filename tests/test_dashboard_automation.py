"""`GET /api/dashboard/automation` (SPEC-016)."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient, PendingAction, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="dash-auto-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Dash", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_automation_dashboard_empty_state(client):
    headers = await _clinician(client)
    res = await client.get("/api/dashboard/automation", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["workflows"]["total"] == 0
    assert body["tick_health"]["status"] == "healthy"
    assert body["notifications"]["read_rate"] is None


async def test_automation_dashboard_counts_overdue_steps(client, db_session):
    p = Patient(id="PDASH1", name="Dash Patient", age=40, sex="M", medical_record_number="PT-PDASH1")
    db_session.add(p)
    wf = Workflow(id="WFDASH1", definition_key="alert_refresh", patient_id="PDASH1", status="active")
    db_session.add(wf)
    step = WorkflowStep(
        id="STDASH1", workflow_id="WFDASH1", step_key="refresh", step_type="alert_refresh",
        status="pending", due_at=datetime(2020, 1, 1), run_after=datetime(2020, 1, 1),
    )
    db_session.add(step)
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/automation", headers=headers)
    body = res.json()
    assert body["steps"]["overdue"] == 1
    assert body["tick_health"]["status"] == "behind"


async def test_automation_dashboard_human_intervention_rate(client, db_session):
    p = Patient(id="PDASH2", name="Dash Patient 2", age=41, sex="F", medical_record_number="PT-PDASH2")
    db_session.add(p)
    approved_edited = PendingAction(
        id="PA-E1", patient_id="PDASH2", action_type="followup_day3", draft_text="draft",
        final_text="edited final", status="approved", reviewed_by="someone",
    )
    approved_unedited = PendingAction(
        id="PA-E2", patient_id="PDASH2", action_type="followup_day3", draft_text="draft",
        final_text="draft", status="approved", reviewed_by="someone",
    )
    db_session.add_all([approved_edited, approved_unedited])
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.get("/api/dashboard/automation", headers=headers)
    body = res.json()
    assert body["approvals"]["approved_edited"] == 1
    assert body["approvals"]["approved_unedited"] == 1
    assert body["approvals"]["human_intervention_rate"] == 0.5
