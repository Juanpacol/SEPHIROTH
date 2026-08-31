"""Patient endpoints — CRUD + Intelligent Timeline, backed by Postgres."""

import logging
import secrets
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.audit import log_phi_access
from api.workflows.channels import get_channel
from auth.deps import get_current_user
from auth.security import hash_password
from core.db import SessionLocal, get_session
from data.schemas import ClinicalNote, Patient, PatientInvite, TimelineEvent, User
from sephiroth.models import get_llm_client
from sephiroth.safety.risk import RISK_ORDER, assess_patient_risk, assess_risk_level

logger = logging.getLogger("api.patients")

INVITE_TTL = timedelta(hours=72)
_MAX_NOTE_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — same ceiling as medical.py's imaging upload

router = APIRouter()


def _summary(patient: Patient, flags: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    if flags is None:
        flags = assess_patient_risk(patient.lab_results, patient.medications)
    return {
        "id": patient.id,
        "name": patient.name,
        "age": patient.age,
        "sex": patient.sex,
        "medical_record_number": patient.medical_record_number,
        "conditions": patient.conditions,
        "status": patient.status,
        "risk_level": assess_risk_level(flags),
    }


def _event(event: TimelineEvent) -> Dict[str, Any]:
    return {
        "date": event.date.isoformat(),
        "type": event.type,
        "title": event.title,
        "detail": event.detail,
        "ai_generated": event.ai_generated,
    }


def _full(patient: Patient) -> Dict[str, Any]:
    flags = assess_patient_risk(patient.lab_results, patient.medications)
    return {
        **_summary(patient, flags),
        "medications": patient.medications,
        "allergies": patient.allergies,
        "lab_results": patient.lab_results,
        "risk_flags": flags,
        "timeline": [_event(e) for e in patient.timeline],
    }


class PatientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    age: int = Field(..., ge=0, le=130)
    sex: str = Field(..., pattern="^[MF]$")
    conditions: List[str] = []
    medications: List[str] = []
    allergies: List[str] = []


@router.get("")
async def list_patients(
    sort: Optional[str] = None, session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    """`sort=risk` reorders the (still name-sorted-first) list by risk level,
    highest first — used by the dashboard's critical-patients view. Omitting
    it keeps the original alphabetical-by-name order unchanged."""
    patients = (await session.scalars(select(Patient).order_by(Patient.name))).all()
    summaries = [_summary(p) for p in patients]
    if sort == "risk":
        summaries.sort(key=lambda s: RISK_ORDER.get(s["risk_level"], len(RISK_ORDER)))
    return summaries


@router.post("", status_code=201)
async def create_patient(body: PatientCreate, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    patient = Patient(
        id=f"P{uuid4().hex[:6].upper()}",
        medical_record_number=f"PT-{uuid4().hex[:5].upper()}",
        lab_results={},
        **body.model_dump(),
    )
    session.add(patient)
    await session.commit()
    # A brand-new patient has no timeline yet, but `commit()` expires every
    # attribute by default; touching `patient.timeline` afterward would
    # trigger an implicit lazy-load outside an awaited context, which
    # asyncpg's async dialect rejects (`MissingGreenlet`) — SQLite's driver
    # tolerates it, so this only ever surfaced against real Postgres.
    # `refresh(..., attribute_names=...)` loads it explicitly, in-band.
    await session.refresh(patient, attribute_names=["timeline"])
    return _full(patient)


async def _get_patient(session: AsyncSession, patient_id: str) -> Patient:
    patient = await session.scalar(
        select(Patient).where(Patient.id == patient_id).options(selectinload(Patient.timeline))
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    patient = await _get_patient(session, patient_id)
    await log_phi_access(session, user, patient_id, "/api/patients/{patient_id}", "GET")
    return _full(patient)


class NoteCreate(BaseModel):
    content: str = Field(..., min_length=10)
    note_type: str = "progress_note"
    note_date: Optional[str] = Field(None, description="ISO date the note refers to; defaults to today")


async def _extract_events_background(patient_id: str, content: str, resolved_date: str) -> None:
    """Phase 2 of the note pipeline, run after the HTTP response is already
    sent (see `_ingest_note`). The LLM call here is the slow, variable part
    (~10s-90s+ on a local model) — running it in the request/response cycle
    made the dev proxy time out and return a false failure to the clinician
    while the backend kept working underneath; the note was always saved
    either way, just the extracted events arrived after the UI had already
    given up. Failures here are logged and swallowed — the note itself is
    already persisted, so there's nothing to roll back."""
    from intelligence.nlp.timeline_extractor import extract_events

    try:
        extracted = await extract_events(get_llm_client(), content, resolved_date)
    except Exception:
        logger.exception("Background timeline extraction failed for patient %s", patient_id)
        return

    if not extracted:
        return

    async with SessionLocal() as session:
        patient = await session.scalar(
            select(Patient).where(Patient.id == patient_id).options(selectinload(Patient.timeline))
        )
        if patient is None:
            return  # patient deleted while extraction was in flight

        # Dedupe against existing events on (date, title).
        existing = {(e.date.isoformat(), e.title.lower()) for e in patient.timeline}
        new_events: List[TimelineEvent] = []
        for event in extracted:
            key = (event.date, event.title.lower())
            if key in existing:
                continue
            existing.add(key)
            new_events.append(
                TimelineEvent(
                    patient_id=patient_id,
                    date=date_cls.fromisoformat(event.date),
                    type=event.type,
                    title=event.title,
                    detail=event.detail,
                    ai_generated=True,
                )
            )
        session.add_all(new_events)
        await session.commit()


async def _ingest_note(
    patient: Patient,
    user: User,
    content: str,
    note_type: str,
    note_date: Optional[str],
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Shared note pipeline, phase 1: lexicon entity extraction (fast, no
    network) and persisting the note row — returns in well under a second
    regardless of LLM latency. The slow part (LLM timeline-event extraction)
    is hand off to `_extract_events_background` via `background_tasks`, so
    this response is never held open waiting on it (see that function's
    docstring for why that matters)."""
    from sephiroth.tools import get_tool_runtime

    resolved_date = note_date or datetime.now(timezone.utc).date().isoformat()

    registry = get_tool_runtime()
    await registry.load()
    entities = await registry.execute("extract_medical_entities", {"text": content})

    note = ClinicalNote(
        id=str(uuid4()),
        patient_id=patient.id,
        user_id=user.id,
        note_type=note_type,
        content=content,
        extracted_entities=entities,
    )

    async with SessionLocal() as session:
        session.add(note)
        await session.commit()

    background_tasks.add_task(_extract_events_background, patient.id, content, resolved_date)

    return {
        "note_id": note.id,
        "entities_found": len(entities.get("entities", [])),
        "events_added": [],
        "processing": True,
    }


@router.post("/{patient_id}/notes", status_code=201, summary="Add a clinical note (text)")
async def add_clinical_note(
    patient_id: str,
    body: NoteCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Store a clinical note and auto-extract Intelligent Timeline events
    (the extraction itself runs in the background — see `_ingest_note`)."""
    async with SessionLocal() as session:
        patient = await _get_patient(session, patient_id)
    return await _ingest_note(patient, user, body.content, body.note_type, body.note_date, background_tasks)


class MedicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    dosage: str = Field("", max_length=60)


@router.post(
    "/{patient_id}/medications",
    status_code=201,
    summary="Prescribe a new medication (notifies the patient portal, if claimed)",
)
async def add_medication(
    patient_id: str,
    body: MedicationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """The only place `Patient.medications` changes after patient
    creation — there was no endpoint for this before (only set once, at
    `POST /api/patients`). Appends the new entry and, if this patient has
    claimed a portal login (`PatientInvite` redemption), notifies them
    in-app via the same `NotificationChannel` seam `scheduling.py`/
    `results.py` already use. Silent no-op on the notification side if no
    portal account exists yet -- prescribing a medication must never fail
    because the patient hasn't claimed their account. Uses the injectable
    `Depends(get_session)` (not `SessionLocal()` directly) so this is
    exercised against the test DB, same as scheduling.py/results.py."""
    entry = f"{body.name.strip()} {body.dosage.strip()}".strip()

    patient = await _get_patient(session, patient_id)
    patient.medications = [*patient.medications, entry]
    await session.commit()

    portal_user = await session.scalar(
        select(User).where(User.patient_id == patient_id, User.role == "patient")
    )
    if portal_user is not None:
        await get_channel().send(
            session,
            portal_user.id,
            "medication_prescribed",
            f"Your clinician prescribed a new medication: {entry}",
        )
        await session.commit()

    return {"medications": patient.medications}


@router.post("/{patient_id}/notes/upload", status_code=201, summary="Upload a clinical note as PDF")
async def upload_clinical_note(
    patient_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    note_type: str = Form("progress_note"),
    note_date: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Extract text from an uploaded PDF and run the same note pipeline."""
    from io import BytesIO

    from fastapi.concurrency import run_in_threadpool
    from pypdf import PdfReader

    async with SessionLocal() as session:
        patient = await _get_patient(session, patient_id)

    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_NOTE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 20 MB limit")
        chunks.append(chunk)
    raw = b"".join(chunks)

    def _extract_text() -> str:
        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()

    try:
        # pypdf is pure-Python and CPU-bound — a large PDF would otherwise
        # stall the single event loop for every other in-flight request.
        text = await run_in_threadpool(_extract_text)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read this file as a PDF.")

    if len(text) < 20:
        raise HTTPException(
            status_code=422,
            detail=(
                "This looks like a scanned PDF — text extraction found no content; "
                "OCR is not supported yet. Paste the note text instead."
            ),
        )

    result = await _ingest_note(patient, user, text, note_type, note_date, background_tasks)
    result["source_file"] = file.filename
    result["characters_extracted"] = len(text)
    return result


@router.get("/{patient_id}/timeline")
async def get_timeline(
    patient_id: str,
    event_type: Optional[str] = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    patient = await _get_patient(session, patient_id)
    await log_phi_access(session, user, patient_id, "/api/patients/{patient_id}/timeline", "GET")
    events = patient.timeline
    if event_type:
        events = [e for e in events if e.type == event_type]
    return {"patient_id": patient_id, "events": [_event(e) for e in events]}


class TimelineEventCreate(BaseModel):
    date: Optional[str] = Field(None, description="ISO date the event refers to; defaults to today")
    type: str = "imaging"
    title: str = Field(..., min_length=1)
    detail: str = ""


@router.post("/{patient_id}/timeline", status_code=201, summary="Add one timeline event directly")
async def add_timeline_event(
    patient_id: str,
    body: TimelineEventCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Direct single-event write — unlike `_ingest_note`'s bulk NLP
    extraction, the caller already knows exactly what happened (e.g. the
    `/imaging` page attaching a vision description). Same dedup rule as
    notes: one event per (date, title) pair."""
    patient = await _get_patient(session, patient_id)
    resolved_date = body.date or datetime.now(timezone.utc).date().isoformat()
    existing = {(e.date.isoformat(), e.title.lower()) for e in patient.timeline}
    if (resolved_date, body.title.lower()) in existing:
        raise HTTPException(status_code=409, detail="An event with this date and title already exists")

    event = TimelineEvent(
        patient_id=patient.id,
        date=date_cls.fromisoformat(resolved_date),
        type=body.type,
        title=body.title,
        detail=body.detail,
        ai_generated=True,
    )
    session.add(event)
    # `patient.timeline` was already loaded (via `_get_patient`'s selectinload)
    # before this event existed; with `expire_on_commit=False` a plain
    # `commit()` doesn't invalidate that already-loaded collection, so a
    # later request reusing this same identity-mapped `Patient` (same
    # session/connection pool) would see a stale, event-missing timeline.
    # Appending here keeps the in-memory relationship state correct
    # regardless of expiration settings.
    patient.timeline.append(event)
    await session.commit()
    return _event(event)


@router.post("/{patient_id}/invites", status_code=201, summary="Issue a patient-portal claim code")
async def create_invite(
    patient_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Issue a one-time, expiring code a patient redeems at
    `POST /api/auth/portal/claim` to create their own portal login.
    There is no patient self-registration — a clinician who has already
    identity-proofed the patient in clinic is the only source of this
    code. Returned once, in this response, never again; the code is
    hashed at rest (`PatientInvite.code_hash`), so losing it means
    issuing a new one, not looking the old one up."""
    await _get_patient(session, patient_id)  # 404 if the chart doesn't exist

    invite = PatientInvite(
        id=str(uuid4()),
        patient_id=patient_id,
        code_hash="",  # set below, once `secret` is known
        issued_by_user_id=user.id,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + INVITE_TTL,
    )
    secret = secrets.token_urlsafe(16)
    invite.code_hash = await hash_password(secret)
    session.add(invite)
    await session.commit()

    return {
        "invite_id": invite.id,
        "code": f"{invite.id}.{secret}",
        "expires_at": invite.expires_at.isoformat(),
    }
