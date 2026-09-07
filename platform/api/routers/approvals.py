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
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.db import SYSTEM_WORKFLOW_USER_ID, get_session
from data.schemas import Patient, PendingAction, User
from sephiroth.models import LLMUnavailableError
from sephiroth.safety import check_input

from ..workflows.channels import get_channel

router = APIRouter()


def _assert_real_reviewer(clinician: User) -> None:
    """Defense-in-depth: `pending_actions.reviewed_by` is FK'd to
    `users.id`, not role-constrained (the DB constraint proves *someone*
    reviewed, not *a clinician*). `require_clinician` already makes this
    branch unreachable in practice -- `system-workflow` has `role`
    `"clinician"` but `is_active=False`, and `get_current_user` rejects
    an inactive user before this dependency ever runs -- but an explicit
    check here means a future change to that dependency chain fails
    loudly instead of silently widening who can satisfy the gate."""
    if clinician.id == SYSTEM_WORKFLOW_USER_ID or clinician.role != "clinician":
        raise HTTPException(status_code=403, detail="Only a real clinician account may review this action")


def _action_out(action: PendingAction, patient_name: Optional[str] = None) -> Dict[str, Any]:
    # `proposed_payload["instructions"]` is the clinician's own note from
    # when they started the follow-up plan (`instructions` on `FollowupPlan`,
    # see `patient_followup.py::enroll_plan`) -- the one piece of context
    # that says *why* this specific check-in exists, not just that it does.
    payload = action.proposed_payload or {}
    return {
        "id": action.id,
        "workflow_step_id": action.workflow_step_id,
        "patient_id": action.patient_id,
        "patient_name": patient_name,
        "action_type": action.action_type,
        "instructions": payload.get("instructions") or None,
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


async def _patient_names(session: AsyncSession, patient_ids: List[str]) -> Dict[str, str]:
    if not patient_ids:
        return {}
    rows = (
        await session.execute(select(Patient.id, Patient.name).where(Patient.id.in_(set(patient_ids))))
    ).all()
    return dict(rows)  # type: ignore[arg-type]


async def _expire_if_due(session: AsyncSession, action: PendingAction, now: datetime) -> None:
    if action.status == "pending" and action.expires_at is not None and action.expires_at < now:
        action.status = "expired"


async def _expire_due_pending(session: AsyncSession, now: datetime) -> int:
    """Bulk flip, not a per-row Python loop over every action in the
    table: a single `UPDATE ... WHERE` handles expiry for every caller
    (list/count) without loading `draft_text`/`proposed_payload` for
    rows nobody asked about. Returns the number of rows flipped."""
    result = await session.execute(
        update(PendingAction)
        .where(
            PendingAction.status == "pending",
            PendingAction.expires_at.is_not(None),
            PendingAction.expires_at < now,
        )
        .values(status="expired")
    )
    if result.rowcount:
        await session.commit()
    return result.rowcount or 0


@router.get("")
async def list_pending_actions(
    status_filter: Optional[str] = Query(None, alias="status"),
    patient_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await _expire_due_pending(session, now)

    stmt = select(PendingAction).order_by(PendingAction.created_at.desc()).limit(limit)
    if patient_id is not None:
        stmt = stmt.where(PendingAction.patient_id == patient_id)
    if status_filter is not None:
        stmt = stmt.where(PendingAction.status == status_filter)
    actions = (await session.scalars(stmt)).all()
    names = await _patient_names(session, [a.patient_id for a in actions])
    return [_action_out(a, names.get(a.patient_id)) for a in actions]


@router.get("/count")
async def count_pending_actions(
    status_filter: str = Query("pending", alias="status"),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await _expire_due_pending(session, now)
    count = (
        await session.scalar(
            select(func.count()).select_from(PendingAction).where(PendingAction.status == status_filter)
        )
    ) or 0
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
    patient = await session.get(Patient, action.patient_id)
    patient_name = patient.name if patient else None
    if action.draft_text:
        return _action_out(action, patient_name)

    first_name = patient.name.split(" ")[0] if patient and patient.name else "there"
    facts = {k: v for k, v in action.proposed_payload.items() if k != "followup_plan_id"}

    # `instructions` is up to 2000 chars of clinician free text
    # (followups.py's CreateFollowupPlanRequest), interpolated straight
    # into the drafting prompt below (patient_comms_server._build_prompt).
    # check_input is the same heuristic runtime/executor.py applies to a
    # consultation query -- reused here because this is the other place
    # free text reaches an LLM prompt in this codebase, just reachable
    # from a routine click on a follow-up plan rather than an explicit
    # consultation.
    instructions = facts.get("instructions")
    if isinstance(instructions, str) and check_input(instructions):
        raise HTTPException(
            status_code=422, detail="Follow-up instructions matched a prompt-injection heuristic pattern"
        )

    try:
        draft = await draft_message(purpose=action.action_type, patient_first_name=first_name, facts=facts)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"Draft generation unavailable: {exc}")

    from core.config import settings

    action.draft_text = draft
    action.draft_model = settings.gemini_model
    await session.commit()
    return _action_out(action, patient_name)


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: str,
    body: ApproveRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    _assert_real_reviewer(clinician)
    action = await _get_action(session, action_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await _expire_if_due(session, action, now)
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {action.status}")

    final_text = body.final_text if body.final_text is not None else action.draft_text
    if check_input(final_text):
        raise HTTPException(
            status_code=422, detail="Approved text matched a prompt-injection heuristic pattern"
        )

    action.final_text = final_text
    action.status = "approved"
    action.reviewed_by = clinician.id
    action.reviewed_at = now

    # The send path (SPEC-013's whole point): this is the first and only
    # place `final_text` reaches a patient. A patient without a portal
    # account (no linked User row -- not every Patient has one, see
    # decision #20) has no channel to receive it; the approval still
    # records the clinician's decision, it just has nowhere to deliver.
    recipient = await session.scalar(
        select(User.id).where(User.patient_id == action.patient_id, User.role == "patient")
    )
    if recipient is not None:
        await get_channel().send(
            session,
            recipient,
            "followup_message",
            final_text,
            dedupe_key=f"pending_action:{action.id}",
        )

    await session.commit()
    return _action_out(action)


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: str,
    body: RejectRequest,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    _assert_real_reviewer(clinician)
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
