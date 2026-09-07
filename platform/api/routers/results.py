"""Exam-results sharing — a clinician shares one `TimelineEvent` (a lab or
imaging result) with the patient it belongs to. See `ResultShare`'s
docstring in `data.schemas` for why it references the existing timeline
rather than inventing a third "lab result" concept.

Every patient-facing read is scoped to the caller's own `patient_id` —
never a client-supplied one — same isolation discipline as `portal.py`
and `scheduling.py`.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from api.audit import log_phi_access
from api.pdf_export import render_result_share_pdf
from auth.deps import get_current_user, require_clinician
from core.db import get_session
from core.storage import get_blob_store
from data.schemas import Notification, Patient, ResultAttachment, ResultShare, TimelineEvent, User
from sephiroth.workflows import events as workflow_events

router = APIRouter()

SHAREABLE_TYPES = ("lab", "imaging")
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ATTACHMENTS_PER_SHARE = 3
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    timeline_event_id: int
    message: str = ""


class ShareUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=0)


def _event_out(event: TimelineEvent) -> Dict[str, Any]:
    return {
        "date": event.date.isoformat(),
        "type": event.type,
        "title": event.title,
        "detail": event.detail,
        "ai_generated": event.ai_generated,
    }


def _attachment_out(att: ResultAttachment) -> Dict[str, Any]:
    return {
        "id": att.id,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
    }


def _share_out(share: ResultShare) -> Dict[str, Any]:
    return {
        "id": share.id,
        "status": share.status,
        "message": share.message,
        "shared_at": share.shared_at.isoformat(),
        "viewed_at": share.viewed_at.isoformat() if share.viewed_at else None,
        "event": _event_out(share.event),
        "attachments": [_attachment_out(a) for a in share.attachments],
    }


@router.get("/shareable/{patient_id}")
async def list_shareable_events(
    patient_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    patient = await session.scalar(
        select(Patient).where(Patient.id == patient_id).options(selectinload(Patient.timeline))
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    already_shared = {
        row.timeline_event_id
        for row in (
            await session.scalars(select(ResultShare).where(ResultShare.patient_id == patient_id))
        ).all()
    }
    return [
        {**_event_out(e), "timeline_event_id": e.id, "already_shared": e.id in already_shared}
        for e in patient.timeline
        if e.type in SHAREABLE_TYPES
    ]


@router.post("/shares", status_code=201)
async def create_share(
    body: ShareCreate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    event = await session.get(TimelineEvent, body.timeline_event_id)
    if event is None or event.patient_id != body.patient_id:
        raise HTTPException(status_code=422, detail="Timeline event does not belong to this patient")
    if event.type not in SHAREABLE_TYPES:
        raise HTTPException(status_code=422, detail=f"Only {SHAREABLE_TYPES} events can be shared")

    existing = await session.scalar(
        select(ResultShare).where(
            ResultShare.timeline_event_id == body.timeline_event_id,
            ResultShare.patient_id == body.patient_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This result has already been shared")

    share = ResultShare(
        id=str(uuid4()),
        patient_id=body.patient_id,
        timeline_event_id=body.timeline_event_id,
        shared_by_user_id=clinician.id,
        message=body.message,
    )
    session.add(share)
    if event.type == "lab":
        workflow_events.emit(
            session,
            workflow_events.LAB_RESULT_AVAILABLE,
            "result_share",
            share.id,
            patient_id=body.patient_id,
        )
    await session.commit()
    await session.refresh(share, attribute_names=["event", "attachments"])

    patient_login = await session.scalar(select(User).where(User.patient_id == body.patient_id))
    if patient_login is not None:
        session.add(
            Notification(
                id=str(uuid4()),
                user_id=patient_login.id,
                type="result_shared",
                message="A new result has been shared with you.",
            )
        )
        await session.commit()
    await log_phi_access(session, clinician, share.patient_id, "/api/results/shares", "POST")
    return _share_out(share)


async def _get_share_for_clinician(session: AsyncSession, share_id: str) -> ResultShare:
    share = await session.scalar(
        select(ResultShare)
        .where(ResultShare.id == share_id)
        .options(selectinload(ResultShare.event), selectinload(ResultShare.attachments))
    )
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@router.patch("/shares/{share_id}")
async def update_share(
    share_id: str,
    body: ShareUpdate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    share = await _get_share_for_clinician(session, share_id)
    share.message = body.message
    await session.commit()
    return _share_out(share)


@router.post("/shares/{share_id}/attachments", status_code=201)
async def upload_attachment(
    share_id: str,
    file: UploadFile,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    share = await _get_share_for_clinician(session, share_id)
    if len(share.attachments) >= MAX_ATTACHMENTS_PER_SHARE:
        raise HTTPException(
            status_code=422, detail=f"A share may carry at most {MAX_ATTACHMENTS_PER_SHARE} attachments"
        )
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {file.content_type}")

    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Attachment exceeds the 10 MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)

    attachment = ResultAttachment(
        id=str(uuid4()),
        result_share_id=share_id,
        filename=file.filename or "attachment",
        content_type=file.content_type,
        size_bytes=total,
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by_user_id=clinician.id,
    )
    session.add(attachment)
    await session.flush()  # attachment.id must exist before blob_store keys on it
    await get_blob_store().put(session, attachment.id, data)
    await session.commit()
    return _attachment_out(attachment)


@router.get("/shares")
async def list_shares(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(ResultShare).options(selectinload(ResultShare.event), selectinload(ResultShare.attachments))
    if user.role == "patient":
        stmt = stmt.where(ResultShare.patient_id == user.patient_id, ResultShare.status == "sent")
    else:
        if patient_id is None:
            raise HTTPException(status_code=422, detail="patient_id is required")
        stmt = stmt.where(ResultShare.patient_id == patient_id)
    shares = (await session.scalars(stmt.order_by(ResultShare.shared_at.desc()))).all()
    return [_share_out(s) for s in shares]


async def _get_own_share(session: AsyncSession, user: User, share_id: str) -> ResultShare:
    share = await session.scalar(
        select(ResultShare)
        .where(ResultShare.id == share_id)
        .options(selectinload(ResultShare.event), selectinload(ResultShare.attachments))
    )
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    if user.role == "patient" and (share.patient_id != user.patient_id or share.status != "sent"):
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@router.get("/shares/{share_id}")
async def get_share(
    share_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    share = await _get_own_share(session, user, share_id)
    if user.role == "patient" and share.viewed_at is None:
        from datetime import datetime, timezone

        share.viewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await log_phi_access(session, user, share.patient_id, "/api/results/shares/{share_id}", "GET")
    return _share_out(share)


@router.get("/shares/{share_id}/pdf", summary="Download a shared result as a PDF")
async def download_share_pdf(
    share_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Renders the shared result (clinician message + result detail) as a
    PDF the patient can save or print — separate from
    `/attachments/{id}/download`, which serves files the clinician
    attached, not the result content itself."""
    share = await _get_own_share(session, user, share_id)
    patient = await session.get(Patient, share.patient_id)
    await log_phi_access(session, user, share.patient_id, "/api/results/shares/{share_id}/pdf", "GET")
    # reportlab's SimpleDocTemplate.build() is synchronous and CPU-bound —
    # offload it so one export doesn't stall every other in-flight request
    # on the single-worker event loop (same reasoning as the consultation
    # PDF export in routers/agents.py).
    pdf_bytes = await run_in_threadpool(render_result_share_pdf, share, patient.name if patient else "")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="resultado-{share.id[:8]}.pdf"'},
    )


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    attachment = await session.get(ResultAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    share = await session.get(ResultShare, attachment.result_share_id)
    if share is None or (
        user.role == "patient" and (share.patient_id != user.patient_id or share.status != "sent")
    ):
        raise HTTPException(status_code=404, detail="Attachment not found")

    data = await get_blob_store().get(session, attachment_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await log_phi_access(
        session, user, share.patient_id, "/api/results/attachments/{attachment_id}/download", "GET"
    )
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(
    share_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> None:
    share = await _get_share_for_clinician(session, share_id)
    share.status = "revoked"
    await session.commit()
