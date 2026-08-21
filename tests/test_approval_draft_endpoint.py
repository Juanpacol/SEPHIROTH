"""`POST /api/approvals/{id}/draft` (SPEC-014) — on-demand LLM drafting,
never from the tick."""

import pytest
from httpx import ASGITransport, AsyncClient

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


async def _clinician(client, email="draft-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Draft", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def llm_action(db_session):
    p = Patient(id="PDRAFT1", name="Draft Patient", age=48, sex="M", medical_record_number="PT-PDRAFT1")
    db_session.add(p)
    action = PendingAction(
        id="PADRAFT1", patient_id="PDRAFT1", action_type="followup_day3", draft_text="",
        draft_source="llm", proposed_payload={"check": "day3", "instructions": "rest"},
    )
    db_session.add(action)
    await db_session.commit()
    return action


async def test_draft_fills_in_text(client, llm_action, patch_llm_factory):
    patch_llm_factory.default_script = [("answer", "Hi! Just checking how you're feeling since your visit.")]
    headers = await _clinician(client)

    res = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)

    assert res.status_code == 200
    assert res.json()["draft_text"] == "Hi! Just checking how you're feeling since your visit."
    assert res.json()["draft_model"]


async def test_draft_is_idempotent_no_second_llm_call(client, llm_action, patch_llm_factory):
    patch_llm_factory.default_script = [("answer", "First draft.")]
    headers = await _clinician(client)

    first = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)
    second = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)

    assert first.json()["draft_text"] == "First draft."
    assert second.json()["draft_text"] == "First draft."
    assert len(patch_llm_factory.chat_calls) == 1


async def test_draft_rejected_for_template_source_action(client, db_session):
    p = Patient(id="PDRAFT2", name="Template Patient", age=30, sex="F", medical_record_number="PT-PDRAFT2")
    db_session.add(p)
    action = PendingAction(
        id="PADRAFT2", patient_id="PDRAFT2", action_type="reminder", draft_text="fixed template text",
        draft_source="template",
    )
    db_session.add(action)
    await db_session.commit()
    headers = await _clinician(client)

    res = await client.post("/api/approvals/PADRAFT2/draft", headers=headers)
    assert res.status_code == 409
