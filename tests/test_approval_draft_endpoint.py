"""`POST /api/approvals/{id}/draft` — on-demand LLM drafting, never from the
tick.

The endpoint's job changed in SPEC-020. Every action now arrives with a
deterministic template draft (`ck_pending_action_draft_nonempty` makes that a
schema guarantee, not a convention), so this is an *upgrade* path rather than a
fill-in-the-blank: it accepts a template draft, and an unreachable model leaves
the usable text in place instead of returning 503.

Verifies AC-020-10 (docs/specs/SPEC-020-automation-correctness.md).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient, PendingAction
from sephiroth.models import LLMUnavailableError

pytestmark = pytest.mark.asyncio

TEMPLATE = "Hola,\n\nTe escribimos desde la consulta para saber cómo has seguido."


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
async def template_action(db_session):
    """What the follow-up step now creates: a real draft, source `template`."""
    p = Patient(id="PDRAFT1", name="Draft Patient", age=48, sex="M", medical_record_number="PT-PDRAFT1")
    db_session.add(p)
    action = PendingAction(
        id="PADRAFT1",
        patient_id="PDRAFT1",
        action_type="followup_day3",
        draft_text=TEMPLATE,
        draft_source="template",
        proposed_payload={"check": "day3", "instructions": "rest"},
    )
    db_session.add(action)
    await db_session.commit()
    return action


async def test_upgrades_a_template_draft_to_a_written_one(client, template_action, patch_llm_factory):
    patch_llm_factory.default_script = [("answer", "Hi! Just checking how you're feeling since your visit.")]
    headers = await _clinician(client)

    res = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)

    assert res.status_code == 200
    assert res.json()["draft_text"] == "Hi! Just checking how you're feeling since your visit."
    # The model that actually wrote it — this row is the audit trail for a
    # message sent to a patient, so a hardcoded provider name would be a lie.
    assert res.json()["draft_model"] == patch_llm_factory.model


async def test_is_idempotent_once_upgraded(client, template_action, patch_llm_factory):
    patch_llm_factory.default_script = [("answer", "First draft.")]
    headers = await _clinician(client)

    first = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)
    second = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)

    assert first.json()["draft_text"] == "First draft."
    assert second.json()["draft_text"] == "First draft."
    # Opening the same item twice must never burn quota twice.
    assert len(patch_llm_factory.chat_calls) == 1


async def test_an_unreachable_model_keeps_the_template_instead_of_failing(
    client, template_action, patch_llm_factory, monkeypatch
):
    """A 503 here would tell a clinician the feature is broken, when in fact
    there is already something on the row they can read and send."""

    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("no local model reachable")

    monkeypatch.setattr(patch_llm_factory, "chat", unavailable)
    headers = await _clinician(client)

    res = await client.post("/api/approvals/PADRAFT1/draft", headers=headers)

    assert res.status_code == 200
    assert res.json()["draft_text"] == TEMPLATE
    assert res.json()["draft_source"] == "template"


async def test_refuses_to_redraft_an_action_that_is_no_longer_pending(client, db_session):
    from sqlalchemy import select

    from data.schemas import User

    # The clinician has to exist first: `ck_pending_action_requires_reviewer`
    # fires on the INSERT, so a rejected row cannot be written without one.
    headers = await _clinician(client)
    reviewer = await db_session.scalar(select(User))

    db_session.add(
        Patient(id="PDRAFT2", name="Closed Patient", age=30, sex="F", medical_record_number="PT-PDRAFT2")
    )
    db_session.add(
        PendingAction(
            id="PADRAFT2",
            patient_id="PDRAFT2",
            action_type="reminder",
            draft_text=TEMPLATE,
            draft_source="template",
            status="rejected",
            reviewed_by=reviewer.id,
        )
    )
    await db_session.commit()

    res = await client.post("/api/approvals/PADRAFT2/draft", headers=headers)
    assert res.status_code == 409
