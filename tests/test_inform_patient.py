"""Telling the patient about a result, from the inbox (AB#21).

Builds on the loop in `test_result_loop.py` and the HTTP surface in
`test_results_inbox_router.py`; this is what the new panel relies on: the entry
the portal renders is made when there is none, the patient is notified, and a
result is told once.
"""

from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from api.routers import result_reviews as reviews_module
from auth import router as auth_router_module
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import (
    Notification,
    Patient,
    PhiAccessLog,
    ResultShare,
    TimelineEvent,
    User,
    WorkflowEvent,
)

pytestmark = pytest.mark.asyncio

CREDS = {"email": "inform-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(reviews_module.router, prefix="/api/results")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def headers(client):
    token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def patient(db_session):
    row = Patient(id="PINF1", name="Ana Gómez", age=61, sex="F", medical_record_number="MRN-PINF1")
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.fixture
async def portal_user(db_session, patient):
    user = User(
        id="u-portal-inf",
        email="ana-portal@example.org",
        name="Ana",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=patient.id,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _reviewed(client, headers, patient, disposition="needs_patient_contact", **lab):
    payload = {
        "patient_id": patient.id,
        "test_name": "potassium",
        "value": 6.2,
        "unit": "mEq/L",
        "taken_at": "2026-10-10T08:00:00+00:00",
    }
    payload.update(lab)
    review = (await client.post("/api/results/labs", json=payload, headers=headers)).json()
    await client.post(
        f"/api/results/reviews/{review['id']}/review",
        json={"disposition": disposition, "note": "Avisar"},
        headers=headers,
    )
    return review["id"]


def _url(review_id):
    return f"/api/results/reviews/{review_id}/communicate"


async def _count(db_session, model):
    return (await db_session.execute(select(func.count()).select_from(model))).scalar()


async def test_it_makes_the_timeline_entry_the_portal_renders_when_there_is_none(
    client, headers, patient, db_session
):
    rid = await _reviewed(client, headers, patient)

    res = await client.post(_url(rid), json={"message": "Su potasio está alto."}, headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "communicated" and body["share_id"] and body["closable"] is True
    assert body["needs_communication"] is False
    (event,) = (await db_session.execute(select(TimelineEvent))).scalars().all()
    assert (event.patient_id, event.type, event.title) == (patient.id, "lab", "Potassium: 6.2 mEq/L")
    assert event.date == date(2026, 10, 10)
    share = await db_session.get(ResultShare, body["share_id"])
    assert share.timeline_event_id == event.id and share.message == "Su potasio está alto."
    assert share.shared_by_user_id and share.status == "sent"


async def test_the_entry_names_the_test_in_words_and_carries_no_decision(
    client, headers, patient, db_session
):
    rid = await _reviewed(client, headers, patient, test_name="blood_urea", value=41.5, unit="")

    await client.post(_url(rid), json={"message": "x"}, headers=headers)

    (event,) = (await db_session.execute(select(TimelineEvent))).scalars().all()
    assert event.title == "Blood urea: 41.5"
    assert event.detail == "", "the clinician's note and the classification stay out of the entry"


async def test_the_patient_is_notified_when_they_have_portal_access(
    client, headers, patient, portal_user, db_session
):
    rid = await _reviewed(client, headers, patient)

    res = await client.post(_url(rid), json={"message": "Hola"}, headers=headers)

    assert res.json()["patient_notified"] is True
    (note,) = (await db_session.execute(select(Notification))).scalars().all()
    assert (note.user_id, note.type) == (portal_user.id, "result_shared")


async def test_without_portal_access_it_is_still_recorded_and_says_nobody_was_notified(
    client, headers, patient, db_session
):
    rid = await _reviewed(client, headers, patient)

    res = await client.post(_url(rid), json={"message": "Hola"}, headers=headers)

    assert res.json()["patient_notified"] is False
    assert res.json()["status"] == "communicated"
    assert await _count(db_session, Notification) == 0
    assert await _count(db_session, ResultShare) == 1


async def test_a_lab_emits_the_lab_available_event_once(client, headers, patient, db_session):
    rid = await _reviewed(client, headers, patient)

    await client.post(_url(rid), json={"message": "Hola"}, headers=headers)

    events = (await db_session.execute(select(WorkflowEvent))).scalars().all()
    assert [e.event_type for e in events if e.event_type == "LAB_RESULT_AVAILABLE"] == [
        "LAB_RESULT_AVAILABLE"
    ]
    assert events[-1].patient_id == patient.id


async def test_telling_twice_sends_nothing_the_second_time(client, headers, patient, portal_user, db_session):
    rid = await _reviewed(client, headers, patient)
    await client.post(_url(rid), json={"message": "Hola"}, headers=headers)

    again = await client.post(_url(rid), json={"message": "Hola otra vez"}, headers=headers)

    assert again.status_code == 409 and "already been communicated" in again.json()["detail"]
    assert await _count(db_session, ResultShare) == 1
    assert await _count(db_session, Notification) == 1
    assert await _count(db_session, TimelineEvent) == 1


async def test_an_existing_entry_of_the_patient_can_be_used_instead(client, headers, patient, db_session):
    entry = TimelineEvent(patient_id=patient.id, date=date(2026, 10, 9), type="lab", title="Panel renal")
    db_session.add(entry)
    await db_session.commit()
    rid = await _reviewed(client, headers, patient)

    res = await client.post(
        _url(rid), json={"message": "Hola", "timeline_event_id": entry.id}, headers=headers
    )

    assert res.status_code == 200
    assert await _count(db_session, TimelineEvent) == 1, "no extra entry is made"
    assert (await db_session.get(ResultShare, res.json()["share_id"])).timeline_event_id == entry.id


async def test_another_patients_entry_is_refused(client, headers, patient, db_session):
    other = Patient(id="PINF2", name="Otro", age=40, sex="M", medical_record_number="MRN-PINF2")
    db_session.add(other)
    await db_session.flush()
    foreign = TimelineEvent(patient_id=other.id, date=date(2026, 10, 9), type="lab", title="Ajeno")
    db_session.add(foreign)
    await db_session.commit()
    rid = await _reviewed(client, headers, patient)

    res = await client.post(
        _url(rid), json={"message": "x", "timeline_event_id": foreign.id}, headers=headers
    )

    assert res.status_code == 404
    assert await _count(db_session, ResultShare) == 0


async def test_an_entry_that_was_already_shared_is_refused(client, headers, patient, db_session):
    entry = TimelineEvent(patient_id=patient.id, date=date(2026, 10, 9), type="lab", title="Panel renal")
    db_session.add(entry)
    await db_session.commit()
    first = await _reviewed(client, headers, patient)
    await client.post(_url(first), json={"message": "a", "timeline_event_id": entry.id}, headers=headers)
    second = await _reviewed(client, headers, patient, taken_at="2026-10-11T08:00:00+00:00")

    res = await client.post(
        _url(second), json={"message": "b", "timeline_event_id": entry.id}, headers=headers
    )

    assert res.status_code == 409 and "already been shared" in res.json()["detail"]


async def test_an_unreviewed_result_cannot_be_told_and_leaves_nothing_behind(
    client, headers, patient, db_session
):
    review = (
        await client.post(
            "/api/results/labs",
            json={"patient_id": patient.id, "test_name": "potassium", "value": 6.2, "unit": "mEq/L"},
            headers=headers,
        )
    ).json()

    res = await client.post(_url(review["id"]), json={"message": "Hola"}, headers=headers)

    assert res.status_code == 409
    assert await _count(db_session, TimelineEvent) == 0 and await _count(db_session, ResultShare) == 0
    assert await _count(db_session, Notification) == 0


async def test_once_told_the_decision_can_be_closed(client, headers, patient):
    rid = await _reviewed(client, headers, patient)
    before = await client.post(f"/api/results/reviews/{rid}/close", headers=headers)
    assert before.status_code == 409, "it could not be closed before"

    await client.post(_url(rid), json={"message": "Hola"}, headers=headers)
    after = await client.post(f"/api/results/reviews/{rid}/close", headers=headers)

    assert after.status_code == 200 and after.json()["status"] == "closed"


async def test_an_imaging_result_gets_an_imaging_entry_and_no_lab_event(client, headers, patient, db_session):
    review = (
        await client.post(
            "/api/results/imaging",
            json={"patient_id": patient.id, "modality": "cr", "body_part": "chest", "severity": "review"},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/results/reviews/{review['id']}/review",
        json={"disposition": "needs_patient_contact", "note": "Avisar"},
        headers=headers,
    )

    res = await client.post(_url(review["id"]), json={"message": "Hola"}, headers=headers)

    assert res.status_code == 200
    (event,) = (await db_session.execute(select(TimelineEvent))).scalars().all()
    assert event.type == "imaging" and event.title == "CR chest"
    assert await _count(db_session, WorkflowEvent) == 0


async def test_the_message_is_required_and_capped(client, headers, patient):
    rid = await _reviewed(client, headers, patient)

    assert (await client.post(_url(rid), json={"message": ""}, headers=headers)).status_code == 422
    assert (await client.post(_url(rid), json={"message": "x" * 2001}, headers=headers)).status_code == 422
    assert (await client.post(_url(rid), json={"message": "x" * 2000}, headers=headers)).status_code == 200


async def test_the_access_is_audited(client, headers, patient, db_session):
    rid = await _reviewed(client, headers, patient)

    await client.post(_url(rid), json={"message": "Hola"}, headers=headers)

    rows = (await db_session.execute(select(PhiAccessLog))).scalars().all()
    assert [(r.patient_id, r.method) for r in rows if "communicate" in r.route] == [(patient.id, "POST")]


async def test_only_a_clinician_can_tell(client, headers, patient, portal_user):
    rid = await _reviewed(client, headers, patient)
    patient_token = {"Authorization": f"Bearer {create_access_token(portal_user.id)}"}

    assert (await client.post(_url(rid), json={"message": "x"})).status_code == 401
    assert (await client.post(_url(rid), json={"message": "x"}, headers=patient_token)).status_code in (
        401,
        403,
    )
    assert (await client.post(_url("missing"), json={"message": "x"}, headers=headers)).status_code == 404
