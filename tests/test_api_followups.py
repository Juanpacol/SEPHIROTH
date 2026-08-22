"""`/api/followups` — creating a plan enrolls the patient_followup
workflow in the same transaction (SPEC-014)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.main import app
from core.db import get_session
from data.schemas import Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="followup-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Followup", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def patient_row(db_session):
    p = Patient(
        id="PFUAPI1", name="Followup API Patient", age=61, sex="F", medical_record_number="PT-PFUAPI1"
    )
    db_session.add(p)
    await db_session.commit()
    return p


async def test_create_plan_enrolls_three_steps(client, patient_row, db_session):
    headers = await _clinician(client)
    res = await client.post(
        "/api/followups",
        json={"patient_id": patient_row.id, "instructions": "Monitor blood pressure"},
        headers=headers,
    )
    assert res.status_code == 201
    plan_id = res.json()["id"]

    workflow = (await db_session.scalars(select(Workflow).where(Workflow.followup_plan_id == plan_id))).one()
    steps = (
        await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))
    ).all()
    assert len(steps) == 3


async def test_cancel_plan_cancels_workflow_and_steps(client, patient_row, db_session):
    headers = await _clinician(client)
    create_res = await client.post("/api/followups", json={"patient_id": patient_row.id}, headers=headers)
    plan_id = create_res.json()["id"]

    cancel_res = await client.post(f"/api/followups/{plan_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    workflow = (await db_session.scalars(select(Workflow).where(Workflow.followup_plan_id == plan_id))).one()
    steps = (
        await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))
    ).all()
    assert workflow.status == "cancelled"
    assert all(s.status == "cancelled" for s in steps)


async def test_cannot_cancel_twice(client, patient_row):
    headers = await _clinician(client)
    create_res = await client.post("/api/followups", json={"patient_id": patient_row.id}, headers=headers)
    plan_id = create_res.json()["id"]

    await client.post(f"/api/followups/{plan_id}/cancel", headers=headers)
    second = await client.post(f"/api/followups/{plan_id}/cancel", headers=headers)
    assert second.status_code == 409


async def test_list_filters_by_patient(client, patient_row):
    headers = await _clinician(client)
    await client.post("/api/followups", json={"patient_id": patient_row.id}, headers=headers)

    res = await client.get("/api/followups", params={"patient_id": patient_row.id}, headers=headers)
    assert len(res.json()) == 1
