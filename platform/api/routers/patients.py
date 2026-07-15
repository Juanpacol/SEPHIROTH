"""Patient endpoints — CRUD + Intelligent Timeline, backed by Postgres."""

from datetime import date as date_cls
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.deps import get_current_user
from core.config import settings
from core.db import get_session
from data.schemas import ClinicalNote, Patient, TimelineEvent, User
from intelligence.agents.risk_engine import assess_patient_risk, assess_risk_level
from intelligence.llm import OllamaClient

router = APIRouter()

_client = OllamaClient(host=settings.ollama_host, model=settings.ollama_model)


def _summary(patient: Patient) -> Dict[str, Any]:
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
    return {
        **_summary(patient),
        "medications": patient.medications,
        "allergies": patient.allergies,
        "lab_results": patient.lab_results,
        "risk_flags": assess_patient_risk(patient.lab_results, patient.medications),
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
async def list_patients(session: AsyncSession = Depends(get_session)) -> List[Dict[str, Any]]:
    patients = (await session.scalars(select(Patient).order_by(Patient.name))).all()
    return [_summary(p) for p in patients]


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
    patient.timeline = []
    return _full(patient)


async def _get_patient(session: AsyncSession, patient_id: str) -> Patient:
    patient = await session.scalar(
        select(Patient).where(Patient.id == patient_id).options(selectinload(Patient.timeline))
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}")
async def get_patient(patient_id: str, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    return _full(await _get_patient(session, patient_id))


class NoteCreate(BaseModel):
    content: str = Field(..., min_length=10)
    note_type: str = "progress_note"
    note_date: Optional[str] = Field(None, description="ISO date the note refers to; defaults to today")


async def _ingest_note(
    session: AsyncSession,
    patient: Patient,
    user: User,
    content: str,
    note_type: str,
    note_date: Optional[str],
) -> Dict[str, Any]:
    """Shared note pipeline: persist the note, extract entities, and add
    AI-extracted Intelligent Timeline events (deduped on date+title)."""
    from intelligence.mcp import get_registry
    from intelligence.nlp.timeline_extractor import extract_events

    resolved_date = note_date or datetime.now(timezone.utc).date().isoformat()

    registry = get_registry()
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
    session.add(note)

    extracted = await extract_events(_client, content, resolved_date)

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
                patient_id=patient.id,
                date=date_cls.fromisoformat(event.date),
                type=event.type,
                title=event.title,
                detail=event.detail,
                ai_generated=True,
            )
        )
    session.add_all(new_events)
    await session.commit()

    return {
        "note_id": note.id,
        "entities_found": len(entities.get("entities", [])),
        "events_added": [_event(e) for e in new_events],
    }


@router.post("/{patient_id}/notes", status_code=201, summary="Add a clinical note (text)")
async def add_clinical_note(
    patient_id: str,
    body: NoteCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Store a clinical note and auto-extract Intelligent Timeline events."""
    patient = await _get_patient(session, patient_id)
    return await _ingest_note(session, patient, user, body.content, body.note_type, body.note_date)


@router.post("/{patient_id}/notes/upload", status_code=201, summary="Upload a clinical note as PDF")
async def upload_clinical_note(
    patient_id: str,
    file: UploadFile = File(...),
    note_type: str = Form("progress_note"),
    note_date: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Extract text from an uploaded PDF and run the same note pipeline."""
    from io import BytesIO

    from pypdf import PdfReader

    patient = await _get_patient(session, patient_id)

    raw = await file.read()
    try:
        reader = PdfReader(BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
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

    result = await _ingest_note(session, patient, user, text, note_type, note_date)
    result["source_file"] = file.filename
    result["characters_extracted"] = len(text)
    return result


@router.get("/{patient_id}/timeline")
async def get_timeline(
    patient_id: str,
    event_type: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    patient = await _get_patient(session, patient_id)
    events = patient.timeline
    if event_type:
        events = [e for e in events if e.type == event_type]
    return {"patient_id": patient_id, "events": [_event(e) for e in events]}
