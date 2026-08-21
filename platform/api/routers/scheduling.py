"""Scheduling — clinician working hours, computed slots, and appointments.

Unlike `patients.py`'s hand-built-dict convention, this router uses
`response_model=` for the availability/slot shapes (new, well-defined
payloads worth documenting in OpenAPI) but drops back to hand-built dicts
for `AppointmentOut` — a clinician sees `notes` (their own private
scratch space on the appointment), a patient never does, and expressing
that with two Pydantic models is more ceremony than a `_appointment_out`
helper that takes a `for_patient: bool` flag.

Every appointment read is scoped to the caller's own role identity
(`user.id` for a clinician, `user.patient_id` for a patient) — never a
client-supplied `clinician_id`/`patient_id` query param — same isolation
discipline as `portal.py`.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user, require_clinician
from core.db import get_session
from data.schemas import (
    Appointment,
    AppointmentSeries,
    AppointmentWaitlist,
    AvailabilityException,
    AvailabilityRule,
    Notification,
    Patient,
    User,
)

from sephiroth.workflows import events as workflow_events

from .. import scheduling as slots_module  # platform/api/scheduling.py (pure expand_slots)

router = APIRouter()

BOOKING_HORIZON = timedelta(days=180)
MAX_SERIES_COUNT = 52
FREQUENCY_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 28}


async def _notify(
    session: AsyncSession,
    user_id: str,
    type_: str,
    message: str,
    related_appointment_id: Optional[str] = None,
) -> None:
    session.add(
        Notification(
            id=str(uuid4()),
            user_id=user_id,
            type=type_,
            message=message,
            related_appointment_id=related_appointment_id,
        )
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"
    slot_minutes: int = Field(30, ge=5, le=240)
    effective_from: Optional[date_cls] = None
    effective_to: Optional[date_cls] = None


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: Optional[str] = None
    slot_minutes: Optional[int] = Field(None, ge=5, le=240)
    effective_from: Optional[date_cls] = None
    effective_to: Optional[date_cls] = None
    active: Optional[bool] = None


class ExceptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: datetime
    end_at: datetime
    kind: Literal["block", "open"]
    reason: str = ""


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinician_id: str
    patient_id: str
    start_at: datetime
    mode: Literal["in_person", "telehealth"] = "in_person"
    reason: str = ""


class AppointmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: Optional[datetime] = None
    status: Optional[Literal["completed", "no_show", "booked"]] = None
    mode: Optional[Literal["in_person", "telehealth"]] = None
    notes: Optional[str] = None


class SeriesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinician_id: str
    patient_id: str
    start_at: datetime
    frequency: Literal["weekly", "biweekly", "monthly"]
    occurrence_count: int = Field(..., ge=1, le=MAX_SERIES_COUNT)
    mode: Literal["in_person", "telehealth"] = "in_person"
    reason: str = ""


class WaitlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinician_id: str
    window_start: datetime
    window_end: datetime


def _validate_iana_timezone(tz: str) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz}")


def _parse_time(value: str):
    from datetime import time as time_cls

    hour, _, minute = value.partition(":")
    return time_cls(int(hour), int(minute))


def _rule_out(rule: AvailabilityRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "clinician_id": rule.clinician_id,
        "weekday": rule.weekday,
        "start_time": rule.start_time.strftime("%H:%M"),
        "end_time": rule.end_time.strftime("%H:%M"),
        "timezone": rule.timezone,
        "slot_minutes": rule.slot_minutes,
        "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
        "active": rule.active,
    }


def _exception_out(exc: AvailabilityException) -> Dict[str, Any]:
    return {
        "id": exc.id,
        "clinician_id": exc.clinician_id,
        "start_at": exc.start_at.isoformat(),
        "end_at": exc.end_at.isoformat(),
        "kind": exc.kind,
        "reason": exc.reason,
    }


def _appointment_out(appt: Appointment, *, for_patient: bool, patient_name: str = "") -> Dict[str, Any]:
    out = {
        "id": appt.id,
        "clinician_id": appt.clinician_id,
        "patient_id": appt.patient_id,
        "start_at": appt.start_at.isoformat(),
        "end_at": appt.end_at.isoformat(),
        "status": appt.status,
        "mode": appt.mode,
        "reason": appt.reason,
        "cancellation_reason": appt.cancellation_reason,
        "series_id": appt.series_id,
    }
    if patient_name:
        out["patient_name"] = patient_name
    if not for_patient:
        out["notes"] = appt.notes
    return out


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


@router.get("/availability")
async def get_my_availability(
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    rules = (
        await session.scalars(select(AvailabilityRule).where(AvailabilityRule.clinician_id == clinician.id))
    ).all()
    exceptions = (
        await session.scalars(
            select(AvailabilityException).where(AvailabilityException.clinician_id == clinician.id)
        )
    ).all()
    return {
        "rules": [_rule_out(r) for r in rules],
        "exceptions": [_exception_out(e) for e in exceptions],
    }


@router.post("/availability", status_code=201)
async def create_availability_rule(
    body: RuleCreate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    _validate_iana_timezone(body.timezone)
    start_time = _parse_time(body.start_time)
    end_time = _parse_time(body.end_time)
    if start_time >= end_time:
        raise HTTPException(status_code=422, detail="start_time must be before end_time")

    existing = (
        await session.scalars(
            select(AvailabilityRule).where(
                AvailabilityRule.clinician_id == clinician.id,
                AvailabilityRule.weekday == body.weekday,
                AvailabilityRule.active,
            )
        )
    ).all()
    for other in existing:
        if start_time < other.end_time and end_time > other.start_time:
            raise HTTPException(status_code=422, detail="Overlaps an existing availability window")

    rule = AvailabilityRule(
        id=str(uuid4()),
        clinician_id=clinician.id,
        weekday=body.weekday,
        start_time=start_time,
        end_time=end_time,
        timezone=body.timezone,
        slot_minutes=body.slot_minutes,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
    )
    session.add(rule)
    await session.commit()
    return _rule_out(rule)


async def _get_own_rule(session: AsyncSession, clinician: User, rule_id: str) -> AvailabilityRule:
    rule = await session.scalar(
        select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id, AvailabilityRule.clinician_id == clinician.id
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Availability rule not found")
    return rule


@router.patch("/availability/{rule_id}")
async def update_availability_rule(
    rule_id: str,
    body: RuleUpdate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    rule = await _get_own_rule(session, clinician, rule_id)
    if body.timezone is not None:
        _validate_iana_timezone(body.timezone)
        rule.timezone = body.timezone
    if body.start_time is not None:
        rule.start_time = _parse_time(body.start_time)
    if body.end_time is not None:
        rule.end_time = _parse_time(body.end_time)
    if rule.start_time >= rule.end_time:
        raise HTTPException(status_code=422, detail="start_time must be before end_time")
    if body.slot_minutes is not None:
        rule.slot_minutes = body.slot_minutes
    if body.effective_from is not None:
        rule.effective_from = body.effective_from
    if body.effective_to is not None:
        rule.effective_to = body.effective_to
    if body.active is not None:
        rule.active = body.active
    await session.commit()
    return _rule_out(rule)


@router.delete("/availability/{rule_id}", status_code=204)
async def delete_availability_rule(
    rule_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await _get_own_rule(session, clinician, rule_id)
    await session.delete(rule)
    await session.commit()


@router.post("/exceptions", status_code=201)
async def create_exception(
    body: ExceptionCreate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    if body.start_at >= body.end_at:
        raise HTTPException(status_code=422, detail="start_at must be before end_at")
    exc = AvailabilityException(
        id=str(uuid4()),
        clinician_id=clinician.id,
        start_at=body.start_at,
        end_at=body.end_at,
        kind=body.kind,
        reason=body.reason,
    )
    session.add(exc)
    await session.commit()
    return _exception_out(exc)


@router.delete("/exceptions/{exception_id}", status_code=204)
async def delete_exception(
    exception_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> None:
    exc = await session.scalar(
        select(AvailabilityException).where(
            AvailabilityException.id == exception_id, AvailabilityException.clinician_id == clinician.id
        )
    )
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    await session.delete(exc)
    await session.commit()


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


async def _check_booking_conflicts(
    session: AsyncSession,
    *,
    clinician_id: str,
    patient_id: str,
    start_at: datetime,
    end_at: datetime,
    exclude_appointment_id: Optional[str] = None,
) -> None:
    """Shared by `book_appointment` and `update_appointment` (reschedule) —
    the latter previously had no overlap check at all. Raises 409 on
    either a patient or clinician double-booking; `exclude_appointment_id`
    lets a reschedule check against every *other* booked appointment
    without tripping over its own still-`booked` row."""
    patient_stmt = select(Appointment).where(
        Appointment.patient_id == patient_id,
        Appointment.status == "booked",
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    clinician_stmt = select(Appointment).where(
        Appointment.clinician_id == clinician_id,
        Appointment.status == "booked",
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_appointment_id is not None:
        patient_stmt = patient_stmt.where(Appointment.id != exclude_appointment_id)
        clinician_stmt = clinician_stmt.where(Appointment.id != exclude_appointment_id)

    if await session.scalar(patient_stmt) is not None:
        raise HTTPException(status_code=409, detail="Patient already has an appointment in this window")
    if await session.scalar(clinician_stmt) is not None:
        raise HTTPException(status_code=409, detail="Clinician already has an appointment in this window")


async def _load_clinician_schedule(session: AsyncSession, clinician_id: str, start: date_cls, end: date_cls):
    rules = (
        await session.scalars(select(AvailabilityRule).where(AvailabilityRule.clinician_id == clinician_id))
    ).all()
    exceptions = (
        await session.scalars(
            select(AvailabilityException).where(
                AvailabilityException.clinician_id == clinician_id,
                AvailabilityException.start_at < datetime.combine(end, datetime.min.time()),
                AvailabilityException.end_at > datetime.combine(start, datetime.min.time()),
            )
        )
    ).all()
    appointments = (
        await session.scalars(
            select(Appointment).where(
                Appointment.clinician_id == clinician_id,
                Appointment.status == "booked",
                Appointment.start_at < datetime.combine(end, datetime.min.time()),
                Appointment.end_at > datetime.combine(start, datetime.min.time()),
            )
        )
    ).all()
    return rules, exceptions, appointments


@router.get("/slots")
async def get_slots(
    clinician_id: str = Query(...),
    date_from: date_cls = Query(..., alias="from"),
    date_to: date_cls = Query(..., alias="to"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    if date_to <= date_from:
        raise HTTPException(status_code=422, detail="'to' must be after 'from'")
    rules, exceptions, appointments = await _load_clinician_schedule(
        session, clinician_id, date_from, date_to
    )
    slots = slots_module.expand_slots(rules, exceptions, appointments, date_from, date_to)
    return {
        "clinician_id": clinician_id,
        "slots": [{"start_at": s.start_at.isoformat(), "end_at": s.end_at.isoformat()} for s in slots],
    }


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


@router.get("/appointments")
async def list_appointments(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    status_filter: Optional[str] = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(Appointment)
    if user.role == "clinician":
        stmt = stmt.where(Appointment.clinician_id == user.id)
    else:
        stmt = stmt.where(Appointment.patient_id == user.patient_id)
    if date_from is not None:
        stmt = stmt.where(Appointment.start_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Appointment.start_at < date_to)
    if status_filter is not None:
        stmt = stmt.where(Appointment.status == status_filter)
    appointments = (await session.scalars(stmt.order_by(Appointment.start_at))).all()
    return [_appointment_out(a, for_patient=user.role == "patient") for a in appointments]


@router.post("/appointments", status_code=201)
async def book_appointment(
    body: AppointmentCreate,
    force: bool = Query(False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    if user.role == "patient" and body.patient_id != user.patient_id:
        raise HTTPException(status_code=403, detail="Cannot book an appointment for another patient")
    if force and user.role != "clinician":
        raise HTTPException(status_code=403, detail="Only a clinician may force a booking")

    clinician = await session.scalar(
        select(User).where(User.id == body.clinician_id, User.role == "clinician")
    )
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician not found")
    patient = await session.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    # The API boundary requires an aware datetime — never assume a naive
    # value means UTC — and converts to UTC-naive for storage, matching
    # every other datetime column in this schema.
    if body.start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at must be timezone-aware")
    start_at = body.start_at.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    if start_at < now:
        raise HTTPException(status_code=422, detail="Cannot book an appointment in the past")
    if start_at > now + BOOKING_HORIZON:
        raise HTTPException(status_code=422, detail="Cannot book more than 180 days out")

    day_start = start_at.date()
    day_end = day_start + timedelta(days=1)
    rules, exceptions, _existing = await _load_clinician_schedule(
        session, body.clinician_id, day_start, day_end
    )
    # Working-hours membership is checked against rules/exceptions ONLY —
    # never against existing appointments. Passing `_existing` here would
    # make an already-booked slot look "outside working hours" instead of
    # "conflicting", which is the wrong 422/409 distinction; the explicit
    # conflict queries below are what a caller actually needs to see a 409.
    slots = slots_module.expand_slots(rules, exceptions, [], day_start, day_end)
    matching = next((s for s in slots if s.start_at == start_at), None)
    if matching is None and not force:
        raise HTTPException(status_code=422, detail="Requested time is outside working hours")
    end_at = matching.end_at if matching is not None else start_at + timedelta(minutes=30)

    await _check_booking_conflicts(
        session,
        clinician_id=body.clinician_id,
        patient_id=body.patient_id,
        start_at=start_at,
        end_at=end_at,
    )

    appt = Appointment(
        id=str(uuid4()),
        clinician_id=body.clinician_id,
        patient_id=body.patient_id,
        start_at=start_at,
        end_at=end_at,
        mode=body.mode,
        reason=body.reason,
        created_by_user_id=user.id,
    )
    session.add(appt)
    workflow_events.emit(
        session,
        workflow_events.NEW_APPOINTMENT,
        "appointment",
        appt.id,
        patient_id=appt.patient_id,
        payload={"start_at": appt.start_at.isoformat()},
    )
    try:
        await session.commit()
    except IntegrityError:
        # Last-resort integrity net: the Postgres-only `EXCLUDE USING gist`
        # constraint catching a race the two SELECT-then-check queries
        # above missed (no row locking). The app-level check above is
        # still the primary, UX-facing mechanism — this only fires when
        # two requests interleaved inside the same tiny window.
        await session.rollback()
        raise HTTPException(status_code=409, detail="This slot was just booked by someone else")

    patient_login = await session.scalar(select(User).where(User.patient_id == body.patient_id))
    if patient_login is not None:
        await _notify(
            session,
            patient_login.id,
            "appointment_booked",
            f"Your appointment is confirmed for {appt.start_at.isoformat()}.",
            related_appointment_id=appt.id,
        )
        await session.commit()
    return _appointment_out(appt, for_patient=user.role == "patient")


async def _get_own_appointment(session: AsyncSession, user: User, appointment_id: str) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    owns = (user.role == "clinician" and appt.clinician_id == user.id) or (
        user.role == "patient" and appt.patient_id == user.patient_id
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.patch("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: str,
    body: AppointmentUpdate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Reschedule or mark an appointment's outcome. Clinician-only — a
    patient's only appointment-mutating action is cancel (`DELETE`)."""
    appt = await _get_own_appointment(session, clinician, appointment_id)
    if body.start_at is not None:
        if body.start_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="start_at must be timezone-aware")
        new_start = body.start_at.astimezone(timezone.utc).replace(tzinfo=None)
        duration = appt.end_at - appt.start_at
        new_end = new_start + duration
        if appt.status == "booked":
            await _check_booking_conflicts(
                session,
                clinician_id=appt.clinician_id,
                patient_id=appt.patient_id,
                start_at=new_start,
                end_at=new_end,
                exclude_appointment_id=appt.id,
            )
        appt.start_at = new_start
        appt.end_at = new_end
    if body.status is not None:
        appt.status = body.status
        if body.status == "no_show":
            workflow_events.emit(
                session, workflow_events.MISSED_APPOINTMENT, "appointment", appt.id, patient_id=appt.patient_id
            )
    if body.mode is not None:
        appt.mode = body.mode
    if body.notes is not None:
        appt.notes = body.notes
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This slot was just booked by someone else")
    return _appointment_out(appt, for_patient=False)


@router.delete("/appointments/{appointment_id}", status_code=204)
async def cancel_appointment(
    appointment_id: str,
    reason: str = Query(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    appt = await _get_own_appointment(session, user, appointment_id)
    appt.status = "cancelled"
    appt.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    appt.cancellation_reason = reason
    await session.commit()

    # Synchronous match-on-cancel: the earliest-waiting request whose
    # window contains the now-freed slot gets notified and removed from
    # the waitlist. No auto-booking — the patient must still book the
    # slot themselves, which avoids a silent double-commit race between
    # "notify" and "book" (no background sweep exists to do this lazily).
    match = await session.scalar(
        select(AppointmentWaitlist)
        .where(
            AppointmentWaitlist.clinician_id == appt.clinician_id,
            AppointmentWaitlist.window_start <= appt.start_at,
            AppointmentWaitlist.window_end >= appt.end_at,
        )
        .order_by(AppointmentWaitlist.created_at)
    )
    if match is not None:
        waitlisted_login = await session.scalar(select(User).where(User.patient_id == match.patient_id))
        if waitlisted_login is not None:
            await _notify(
                session,
                waitlisted_login.id,
                "waitlist_match",
                f"A slot opened up at {appt.start_at.isoformat()} — book it before it's gone.",
            )
        await session.delete(match)
        await session.commit()


@router.get("/agenda/today")
async def agenda_today(
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    appointments = (
        await session.scalars(
            select(Appointment)
            .where(
                Appointment.clinician_id == clinician.id,
                Appointment.status == "booked",
                Appointment.start_at >= day_start,
                Appointment.start_at < day_end,
            )
            .order_by(Appointment.start_at)
        )
    ).all()

    patient_names = dict(
        (
            await session.execute(
                select(Patient.id, Patient.name).where(
                    Patient.id.in_({a.patient_id for a in appointments})
                )
            )
        ).all()
    )
    items = [
        {
            "id": appt.id,
            "start_at": appt.start_at.isoformat(),
            "end_at": appt.end_at.isoformat(),
            "patient_name": patient_names.get(appt.patient_id, ""),
            "reason": appt.reason,
        }
        for appt in appointments
    ]

    return {
        "date": today.isoformat(),
        "count": len(items),
        "next_at": items[0]["start_at"] if items else None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# Recurring series
# ---------------------------------------------------------------------------


def _series_out(series: AppointmentSeries, occurrence_ids: List[str]) -> Dict[str, Any]:
    return {
        "id": series.id,
        "clinician_id": series.clinician_id,
        "patient_id": series.patient_id,
        "frequency": series.frequency,
        "occurrence_count": series.occurrence_count,
        "status": series.status,
        "appointment_ids": occurrence_ids,
    }


@router.post("/series", status_code=201)
async def create_series(
    body: SeriesCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Expands every occurrence **eagerly**, all in one transaction — see
    `AppointmentSeries`'s docstring for why (no scheduler process exists
    to expand a series lazily). Every occurrence must land on a real,
    conflict-free working-hours slot or the whole series is rejected —
    partially booking a recurring series would be a worse failure mode
    than rejecting it outright."""
    if user.role == "patient" and body.patient_id != user.patient_id:
        raise HTTPException(status_code=403, detail="Cannot book a series for another patient")

    clinician = await session.scalar(
        select(User).where(User.id == body.clinician_id, User.role == "clinician")
    )
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician not found")
    patient = await session.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    if body.start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at must be timezone-aware")
    first_start = body.start_at.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if first_start < now:
        raise HTTPException(status_code=422, detail="Cannot book an appointment in the past")

    step_days = FREQUENCY_DAYS[body.frequency]
    occurrence_starts: List[datetime] = []
    for i in range(body.occurrence_count):
        occ_start = first_start + timedelta(days=step_days * i)
        if occ_start > now + BOOKING_HORIZON:
            raise HTTPException(status_code=422, detail=f"Occurrence {i + 1} is more than 180 days out")
        occurrence_starts.append(occ_start)

    # Load the schedule and any conflicting appointments once for the whole
    # span instead of once per occurrence (up to 52) — that was up to 260
    # round trips to Supabase in one request. `_load_clinician_schedule`'s
    # own `appointments` return is clinician-scoped only; conflict checking
    # here also needs the patient's appointments with *other* clinicians, so
    # that part is queried separately with an explicit OR.
    span_start = occurrence_starts[0].date()
    span_end = occurrence_starts[-1].date() + timedelta(days=1)
    rules, exceptions, _clinician_appts = await _load_clinician_schedule(
        session, body.clinician_id, span_start, span_end
    )
    conflict_candidates = (
        await session.scalars(
            select(Appointment).where(
                Appointment.status == "booked",
                Appointment.start_at < datetime.combine(span_end, datetime.min.time()),
                Appointment.end_at > datetime.combine(span_start, datetime.min.time()),
                or_(Appointment.clinician_id == body.clinician_id, Appointment.patient_id == body.patient_id),
            )
        )
    ).all()

    all_slots = slots_module.expand_slots(rules, exceptions, [], span_start, span_end)
    slots_by_start = {s.start_at: s for s in all_slots}

    occurrences: List[tuple] = []  # (start_at, end_at)
    for i, occ_start in enumerate(occurrence_starts):
        matching = slots_by_start.get(occ_start)
        if matching is None:
            raise HTTPException(
                status_code=422,
                detail=f"Occurrence {i + 1} ({occ_start.isoformat()}) is outside working hours",
            )
        if any(
            a.start_at < matching.end_at and a.end_at > occ_start for a in conflict_candidates
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Occurrence {i + 1} ({occ_start.isoformat()}) conflicts with an existing appointment",
            )
        occurrences.append((occ_start, matching.end_at))

    series = AppointmentSeries(
        id=str(uuid4()),
        clinician_id=body.clinician_id,
        patient_id=body.patient_id,
        frequency=body.frequency,
        occurrence_count=body.occurrence_count,
        created_by_user_id=user.id,
    )
    session.add(series)
    appointment_ids: List[str] = []
    for occ_start, occ_end in occurrences:
        appt = Appointment(
            id=str(uuid4()),
            clinician_id=body.clinician_id,
            patient_id=body.patient_id,
            start_at=occ_start,
            end_at=occ_end,
            mode=body.mode,
            reason=body.reason,
            created_by_user_id=user.id,
            series_id=series.id,
        )
        session.add(appt)
        appointment_ids.append(appt.id)

    try:
        await session.commit()
    except IntegrityError:
        # Same last-resort backstop as book_appointment — a race across
        # any single occurrence rolls back the entire series.
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="One of these occurrences was just booked by someone else"
        )
    return _series_out(series, appointment_ids)


@router.delete("/series/{series_id}", status_code=204)
async def cancel_series(
    series_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Cancels the series and every future (not past) occurrence — a
    session that already happened stays on the record."""
    series = await session.get(AppointmentSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    owns = (user.role == "clinician" and series.clinician_id == user.id) or (
        user.role == "patient" and series.patient_id == user.patient_id
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Series not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    series.status = "cancelled"
    future_occurrences = (
        await session.scalars(
            select(Appointment).where(
                Appointment.series_id == series_id,
                Appointment.status == "booked",
                Appointment.start_at >= now,
            )
        )
    ).all()
    for appt in future_occurrences:
        appt.status = "cancelled"
        appt.cancelled_at = now
        appt.cancellation_reason = "Recurring series cancelled"
    await session.commit()


# ---------------------------------------------------------------------------
# Waitlist
# ---------------------------------------------------------------------------


def _waitlist_out(entry: AppointmentWaitlist) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "clinician_id": entry.clinician_id,
        "patient_id": entry.patient_id,
        "window_start": entry.window_start.isoformat(),
        "window_end": entry.window_end.isoformat(),
        "created_at": entry.created_at.isoformat(),
    }


@router.post("/waitlist", status_code=201)
async def join_waitlist(
    body: WaitlistCreate,
    patient: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    if patient.role != "patient":
        raise HTTPException(status_code=403, detail="Only a patient may join a waitlist")
    if body.window_start.tzinfo is None or body.window_end.tzinfo is None:
        raise HTTPException(status_code=422, detail="window_start/window_end must be timezone-aware")
    window_start = body.window_start.astimezone(timezone.utc).replace(tzinfo=None)
    window_end = body.window_end.astimezone(timezone.utc).replace(tzinfo=None)
    if window_start >= window_end:
        raise HTTPException(status_code=422, detail="window_start must be before window_end")

    clinician = await session.scalar(
        select(User).where(User.id == body.clinician_id, User.role == "clinician")
    )
    if clinician is None:
        raise HTTPException(status_code=404, detail="Clinician not found")

    entry = AppointmentWaitlist(
        id=str(uuid4()),
        clinician_id=body.clinician_id,
        patient_id=patient.patient_id,
        window_start=window_start,
        window_end=window_end,
    )
    session.add(entry)
    await session.commit()
    return _waitlist_out(entry)


@router.get("/waitlist")
async def list_my_waitlist(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    if user.role == "clinician":
        stmt = select(AppointmentWaitlist).where(AppointmentWaitlist.clinician_id == user.id)
    else:
        stmt = select(AppointmentWaitlist).where(AppointmentWaitlist.patient_id == user.patient_id)
    entries = (await session.scalars(stmt.order_by(AppointmentWaitlist.created_at))).all()
    return [_waitlist_out(e) for e in entries]


@router.delete("/waitlist/{entry_id}", status_code=204)
async def leave_waitlist(
    entry_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    entry = await session.get(AppointmentWaitlist, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    owns = (user.role == "clinician" and entry.clinician_id == user.id) or (
        user.role == "patient" and entry.patient_id == user.patient_id
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    await session.delete(entry)
    await session.commit()
