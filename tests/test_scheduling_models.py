"""Schema-level checks for the 5 new scheduling/results tables — that
`Base.metadata.create_all` builds them on SQLite, constraints fire, and
cascade delete works. API-level behavior lives in
`tests/test_api_scheduling_availability.py`,
`tests/test_api_scheduling_appointments.py`, and
`tests/test_api_result_shares.py`."""

from datetime import date, datetime, time

import pytest
from sqlalchemy.exc import IntegrityError

from data.schemas import (
    Appointment,
    AvailabilityRule,
    Patient,
    ResultAttachment,
    ResultShare,
    TimelineEvent,
    User,
)


@pytest.fixture
async def clinician(db_session):
    from auth.security import hash_password

    user = User(id="clin1", email="clin1@example.org", name="Dr. Model", hashed_password=await hash_password("x"))
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def patient(db_session):
    p = Patient(id="PMODEL1", name="Model Patient", age=40, sex="F", medical_record_number="PT-PMODEL1")
    db_session.add(p)
    await db_session.commit()
    return p


async def test_availability_rule_creates_and_reads_back(db_session, clinician):
    rule = AvailabilityRule(
        id="rule1",
        clinician_id=clinician.id,
        weekday=0,
        start_time=time(9, 0),
        end_time=time(17, 0),
    )
    db_session.add(rule)
    await db_session.commit()
    fetched = await db_session.get(AvailabilityRule, "rule1")
    assert fetched.timezone == "UTC"
    assert fetched.slot_minutes == 30
    assert fetched.active is True


async def test_availability_rule_time_order_check_constraint(db_session, clinician):
    rule = AvailabilityRule(
        id="rule2", clinician_id=clinician.id, weekday=0, start_time=time(17, 0), end_time=time(9, 0)
    )
    db_session.add(rule)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_appointment_time_order_check_constraint(db_session, clinician, patient):
    appt = Appointment(
        id="appt1",
        clinician_id=clinician.id,
        patient_id=patient.id,
        start_at=datetime(2026, 2, 1, 10, 0),
        end_at=datetime(2026, 2, 1, 9, 0),
    )
    db_session.add(appt)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_result_share_unique_per_event_and_patient(db_session, patient):
    event = TimelineEvent(patient_id=patient.id, date=date(2026, 1, 1), type="lab", title="A1C")
    db_session.add(event)
    await db_session.commit()

    from auth.security import hash_password

    user = User(id="clin2", email="clin2@example.org", name="Dr. X", hashed_password=await hash_password("x"))
    db_session.add(user)
    await db_session.commit()

    share1 = ResultShare(
        id="share1", patient_id=patient.id, timeline_event_id=event.id, shared_by_user_id=user.id
    )
    db_session.add(share1)
    await db_session.commit()

    share2 = ResultShare(
        id="share2", patient_id=patient.id, timeline_event_id=event.id, shared_by_user_id=user.id
    )
    db_session.add(share2)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_result_attachment_cascade_deletes_with_share(db_session, patient):
    event = TimelineEvent(patient_id=patient.id, date=date(2026, 1, 1), type="imaging", title="Chest X-ray")
    db_session.add(event)
    await db_session.commit()

    from auth.security import hash_password

    user = User(id="clin3", email="clin3@example.org", name="Dr. Y", hashed_password=await hash_password("x"))
    db_session.add(user)
    await db_session.commit()

    share = ResultShare(
        id="share3", patient_id=patient.id, timeline_event_id=event.id, shared_by_user_id=user.id
    )
    db_session.add(share)
    await db_session.commit()

    attachment = ResultAttachment(
        id="att1",
        result_share_id=share.id,
        filename="scan.pdf",
        content_type="application/pdf",
        size_bytes=3,
        sha256="x" * 64,
        content=b"pdf",
        uploaded_by_user_id=user.id,
    )
    db_session.add(attachment)
    await db_session.commit()

    await db_session.delete(share)
    await db_session.commit()

    assert await db_session.get(ResultAttachment, "att1") is None


async def test_timeline_event_id_is_integer_typed():
    """`ResultShare.timeline_event_id` must be an Integer FK, unlike every
    other FK in this file which is String(36) — `timeline_events.id` is
    an autoincrement Integer PK, an easy type mismatch to introduce."""
    col = ResultShare.__table__.c.timeline_event_id
    assert col.type.python_type is int
