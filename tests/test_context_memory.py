"""`recent_consultation_summaries` — per-patient consultation memory
(F-035's "memory" slice, SPEC-005). Not a session/thread concept — see the
module docstring for why.

Verifies AC-005-03 (docs/specs/SPEC-005-context-engine.md)."""

from uuid import uuid4

import pytest

from data.schemas import Consultation, User
from sephiroth.context.memory import recent_consultation_summaries


async def _user(session) -> User:
    user = User(id=str(uuid4()), email=f"{uuid4()}@example.org", name="Dr. Test", hashed_password="x")
    session.add(user)
    await session.commit()
    return user


async def _consultation(session, user_id, patient_id, query, answer, created_at=None):
    row = Consultation(
        id=str(uuid4()),
        user_id=user_id,
        patient_id=patient_id,
        query=query,
        answer=answer,
        agents=[],
        tool_calls=[],
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_no_patient_id_returns_empty(db_session):
    assert await recent_consultation_summaries("", db_session) == []


@pytest.mark.asyncio
async def test_no_prior_consultations_returns_empty(db_session):
    assert await recent_consultation_summaries("some-patient-id", db_session) == []


@pytest.mark.asyncio
async def test_returns_recent_consultations_newest_first(db_session):
    from datetime import datetime, timedelta, timezone

    user = await _user(db_session)
    patient_id = str(uuid4())
    now = datetime.now(timezone.utc)
    await _consultation(db_session, user.id, patient_id, "first question", "first answer", created_at=now)
    await _consultation(
        db_session,
        user.id,
        patient_id,
        "second question",
        "second answer",
        created_at=now + timedelta(seconds=1),
    )

    summaries = await recent_consultation_summaries(patient_id, db_session, limit=5)

    assert len(summaries) == 2
    assert "second question" in summaries[0]
    assert "first question" in summaries[1]


@pytest.mark.asyncio
async def test_respects_limit(db_session):
    user = await _user(db_session)
    patient_id = str(uuid4())
    for i in range(5):
        await _consultation(db_session, user.id, patient_id, f"question {i}", f"answer {i}")

    summaries = await recent_consultation_summaries(patient_id, db_session, limit=2)
    assert len(summaries) == 2


@pytest.mark.asyncio
async def test_answer_is_excerpted_not_full_text(db_session):
    user = await _user(db_session)
    patient_id = str(uuid4())
    long_answer = "x" * 1000
    await _consultation(db_session, user.id, patient_id, "q", long_answer)

    summaries = await recent_consultation_summaries(patient_id, db_session)
    assert len(summaries[0]) < len(long_answer)


@pytest.mark.asyncio
async def test_only_returns_consultations_for_the_requested_patient(db_session):
    user = await _user(db_session)
    patient_a, patient_b = str(uuid4()), str(uuid4())
    await _consultation(db_session, user.id, patient_a, "question about A", "answer A")
    await _consultation(db_session, user.id, patient_b, "question about B", "answer B")

    summaries = await recent_consultation_summaries(patient_a, db_session)
    assert len(summaries) == 1
    assert "question about A" in summaries[0]
