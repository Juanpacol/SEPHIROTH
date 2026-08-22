"""Approval inbox (SPEC-013) -- the human-in-the-loop gate. Anything a
`PendingAction` row exists for is, by construction, something the
*patient* will see and that no automation is allowed to send on its
own; approve/reject are the only two ways a row leaves `pending`, and
the DB-level `ck_pending_action_requires_reviewer` constraint
(`data/schemas/__init__.py`) makes that true even if a future bug
bypasses this router entirely.

Edit-then-approve is the SAME call as a plain approve (`final_text` is
optional on `POST /{id}/approve`) rather than a separate PATCH+approve
pair -- editing and approving in two requests would leave a real gap
where the draft is edited but not yet approved, and nothing stops it
from being read as final in that window. One call, one transaction.

Expiry is computed at read time (`list_pending_actions`), matching this
codebase's existing convention for `sephiroth.safety.risk` flags
(decision #10) -- no background job flips a row to `expired`; the next
read does.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.db import get_session
from data.schemas import Patient, PendingAction, User
from sephiroth.models import LLMUnavailableError

router = APIRouter()


def _action_out(action: PendingAction) -> Dict[str, Any]:
    return {
        "id": action.id,
        "workflow_step_id": action.workflow_step_id,
        "patient_id": action.patient_id,
        "action_type": action.action_type,
        "status": action.status,
        "draft_text": action.draft_text,
        "draft_source": action.draft_source,
        "draft_model": action.draft_model,
        "final_text": action.final_text,
        "edited": bool(action.final_text) and action.final_text != action.draft_text,
        "assigned_to_user_id": action.assigned_to_user_id,
        "expires_at": action.expires_at.isoformat() if action.expires_at else None,
        "reviewed_by": action.reviewed_by,
        "reviewed_at": action.reviewed_at.isoformat() if action.reviewed_at else None,
        "reject_reason": action.reject_reason,
        "created_at": action.created_at.isoformat(),
    }


async def _expire_if_due(session: AsyncSession, action: PendingAction, now: datetime) -> None:
    if action.status == "pending" and action.expires_at is not None and action.expires_at < now:
        action.status = "expired"


@router.get("")
async def list_pending_actions(
    status_filter: Optional[str] = Query(None, alias="status"),
    patient_id: Optional[str] = None,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(PendingAction).order_by(PendingAction.created_at.desc())
    if patient_id is not None:
        stmt = stmt.where(PendingAction.patient_id == patient_id)
    actions = (await session.scalars(stmt)).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    touched = False
    for action in actions:
        before = action.status
        await _expire_if_due(session, action, now)
        touched = touched or action.status != before
    if touched:
        await session.commit()

    if status_filter is not None:
        actions = [a for a in actions if a.status == status_filter]
    return [_action_out(a) for a in actions]


@router.get("/count")
async def count_pending_actions(
    status_filter: str = Query("pending", alias="status"),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if status_filter == "pending":
        # Expiry is lazy -- exclude anything already past its expires_at
        # rather than lying about the badge count until someone next
        # opens the full list.
        rows = (await session.scalars(select(PendingAction).where(PendingAction.status == "pending"))).all()
        count = sum(1 for a in rows if a.expires_at is None or a.expires_at >= now)
    else:
        count = len(
            (await session.scalars(select(PendingAction).where(PendingAction.status == status_filter))).all()
        )
    return {"count": count}


async def _get_action(session: AsyncSession, action_id: str) -> PendingAction:
    action = await session.get(PendingAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Pending action not found")
    return action


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_text: Optional[str] = None


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=300)


@router.post("/{action_id}/draft")
async def draft_pending_action(
    action_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Generates `draft_text` on demand -- the LLM is never called from
    the tick (SPEC-009); this is the one place drafting actually
    happens, triggered by a clinician opening the queue. Idempotent: a
    second call is a no-op returning the existing draft, so opening the
    same item twice never burns quota twice."""
    from intelligence.mcp.patient_comms_server import draft_message

    action = await _get_action(session, action_id)
    if action.draft_source != "llm":
        raise HTTPException(status_code=409, detail="This action does not use an LLM-generated draft")
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {action.status}")
    if action.draft_text:
        return _action_out(action)

    patient = await session.get(Patient, action.patient_id)
    first_name = patient.name.split(" ")[0] if patient and patient.name else "there"
    facts = {k: v for k, v in action.proposed_payload.items() if k != "followup_plan_id"}

    try:
        draft = await draft_message(purpose=action.action_type, patient_first_name=first_name, facts=facts)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"Draft generation unavailable: {exc}")

    from core.config import settings

    action.draft_text = draft
    action.draft_model = settings.gemini_model
    await session.commit()
    return _action_out(action)


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: str,
    body: ApproveRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    action = await _get_action(session, action_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await _expire_if_due(session, action, now)
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {action.status}")

    action.final_text = body.final_text if body.final_text is not None else action.draft_text
    action.status = "approved"
    action.reviewed_by = clinician.id
    action.reviewed_at = now
    await session.commit()
    return _action_out(action)


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: str,
    body: RejectRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    action = await _get_action(session, action_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await _expire_if_due(session, action, now)
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {action.status}")

    action.status = "rejected"
    action.reviewed_by = clinician.id
    action.reviewed_at = now
    action.reject_reason = body.reason
    await session.commit()
    return _action_out(action)


__all__ = ["router"]
