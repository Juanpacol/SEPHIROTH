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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user, require_clinician
from core.db import get_session
from data.schemas import Appointment, AvailabilityException, AvailabilityRule, Patient, User

from .. import scheduling as slots_module  # platform/api/scheduling.py (pure expand_slots)

router = APIRouter()

BOOKING_HORIZON = timedelta(days=180)


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

    patient_conflict = await session.scalar(
        select(Appointment).where(
            Appointment.patient_id == body.patient_id,
            Appointment.status == "booked",
            Appointment.start_at < end_at,
            Appointment.end_at > start_at,
        )
    )
    if patient_conflict is not None:
        raise HTTPException(status_code=409, detail="Patient already has an appointment in this window")

    clinician_conflict = await session.scalar(
        select(Appointment).where(
            Appointment.clinician_id == body.clinician_id,
            Appointment.status == "booked",
            Appointment.start_at < end_at,
            Appointment.end_at > start_at,
        )
    )
    if clinician_conflict is not None:
        raise HTTPException(status_code=409, detail="Clinician already has an appointment in this window")

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
        appt.start_at = new_start
        appt.end_at = new_start + duration
    if body.status is not None:
        appt.status = body.status
    if body.mode is not None:
        appt.mode = body.mode
    if body.notes is not None:
        appt.notes = body.notes
    await session.commit()
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

    items = []
    for appt in appointments:
        patient = await session.get(Patient, appt.patient_id)
        items.append(
            {
                "id": appt.id,
                "start_at": appt.start_at.isoformat(),
                "end_at": appt.end_at.isoformat(),
                "patient_name": patient.name if patient else "",
                "reason": appt.reason,
            }
        )

    return {
        "date": today.isoformat(),
        "count": len(items),
        "next_at": items[0]["start_at"] if items else None,
        "items": items,
    }
