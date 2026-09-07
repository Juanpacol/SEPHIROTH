"""`/api/approvals` — the human-in-the-loop gate (SPEC-013)."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from api.main import app
from core.db import get_session
from data.schemas import Patient, PendingAction

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="approve-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Approve", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def pending_row(db_session):
    p = Patient(id="PPA1", name="Approval Patient", age=44, sex="M", medical_record_number="PT-PPA1")
    db_session.add(p)
    action = PendingAction(
        id="PA1",
        patient_id="PPA1",
        action_type="followup_message",
        draft_text="Hi, checking in.",
        draft_source="llm",
        draft_model="fake-model",
    )
    db_session.add(action)
    await db_session.commit()
    return action


async def test_approve_without_edit_keeps_draft_text(client, pending_row):
    headers = await _clinician(client)
    res = await client.post("/api/approvals/PA1/approve", json={}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["final_text"] == "Hi, checking in."
    assert body["edited"] is False
    assert body["reviewed_by"] is not None


async def test_approve_with_edit_marks_edited(client, pending_row):
    headers = await _clinician(client)
    res = await client.post(
        "/api/approvals/PA1/approve", json={"final_text": "Hi! Just checking in on you."}, headers=headers
    )
    body = res.json()
    assert body["final_text"] == "Hi! Just checking in on you."
    assert body["edited"] is True


async def test_reject_requires_a_reason(client, pending_row):
    headers = await _clinician(client)
    res = await client.post("/api/approvals/PA1/reject", json={"reason": ""}, headers=headers)
    assert res.status_code == 422


async def test_reject_with_reason(client, pending_row):
    headers = await _clinician(client)
    res = await client.post(
        "/api/approvals/PA1/reject", json={"reason": "not clinically appropriate"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"
    assert res.json()["reject_reason"] == "not clinically appropriate"


async def test_cannot_approve_twice(client, pending_row):
    headers = await _clinician(client)
    await client.post("/api/approvals/PA1/approve", json={}, headers=headers)
    second = await client.post("/api/approvals/PA1/approve", json={}, headers=headers)
    assert second.status_code == 409


async def test_expired_action_cannot_be_approved(client, db_session):
    p = Patient(id="PPA2", name="Expired Patient", age=50, sex="F", medical_record_number="PT-PPA2")
    db_session.add(p)
    action = PendingAction(
        id="PA2",
        patient_id="PPA2",
        action_type="followup_message",
        draft_text="x",
        expires_at=datetime.now() - timedelta(days=1),
    )
    db_session.add(action)
    await db_session.commit()

    headers = await _clinician(client)
    res = await client.post("/api/approvals/PA2/approve", json={}, headers=headers)
    assert res.status_code == 409

    listed = await client.get("/api/approvals", params={"status": "expired"}, headers=headers)
    assert len(listed.json()) == 1


async def test_list_and_count_filter_by_status(client, pending_row):
    headers = await _clinician(client)
    count_res = await client.get("/api/approvals/count", headers=headers)
    assert count_res.json() == {"count": 1}

    await client.post("/api/approvals/PA1/approve", json={}, headers=headers)

    count_after = await client.get("/api/approvals/count", headers=headers)
    assert count_after.json() == {"count": 0}


async def test_list_includes_patient_name_not_just_id(client, pending_row):
    """Regression test: the approvals inbox used to show only the raw
    patient_id — a clinician landing on the page had no idea who a
    pending message was for without cross-referencing another tab."""
    headers = await _clinician(client)
    res = await client.get("/api/approvals", headers=headers)
    body = res.json()
    assert len(body) == 1
    assert body[0]["patient_name"] == "Approval Patient"
    assert body[0]["instructions"] is None  # pending_row sets no proposed_payload


async def test_db_level_constraint_blocks_approved_without_reviewer(db_session):
    """Even bypassing the router entirely, the DB refuses an
    approved/rejected row with no reviewer -- the actual safety
    guarantee, not just the router's own logic."""
    p = Patient(id="PPA3", name="Constraint Patient", age=33, sex="M", medical_record_number="PT-PPA3")
    db_session.add(p)
    bad_action = PendingAction(
        id="PA3",
        patient_id="PPA3",
        action_type="followup_message",
        draft_text="x",
        status="approved",
        reviewed_by=None,
    )
    db_session.add(bad_action)
    with pytest.raises(IntegrityError):
        await db_session.commit()
