"""Post-consultation follow-up plans (SPEC-014). Creating a plan enrolls
the `patient_followup` workflow (day 3/7/30 checks) directly --
`enroll_plan` is called in the same transaction as the plan row, not
triggered via an event, since there is no existing "plan created" event
and this is the only caller that would ever emit one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.db import get_session
from data.schemas import FollowupPlan, Patient, User, Workflow

from ..workflows.instantiate import cancel_workflow
from ..workflows.patient_followup import enroll_plan

router = APIRouter()


def _plan_out(plan: FollowupPlan) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "patient_id": plan.patient_id,
        "consultation_id": plan.consultation_id,
        "created_by_user_id": plan.created_by_user_id,
        "status": plan.status,
        "instructions": plan.instructions,
        "created_at": plan.created_at.isoformat(),
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
    }


class FollowupPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    consultation_id: Optional[str] = None
    instructions: str = Field(default="", max_length=2000)


@router.get("")
async def list_followup_plans(
    patient_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(FollowupPlan).order_by(FollowupPlan.created_at.desc())
    if patient_id is not None:
        stmt = stmt.where(FollowupPlan.patient_id == patient_id)
    if status_filter is not None:
        stmt = stmt.where(FollowupPlan.status == status_filter)
    plans = (await session.scalars(stmt)).all()
    return [_plan_out(p) for p in plans]


@router.post("", status_code=201)
async def create_followup_plan(
    body: FollowupPlanCreate,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    patient = await session.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Set explicitly rather than relying on the server_default -- enroll_plan
    # anchors each check's due_at off plan.created_at in the same
    # transaction, before any round-trip could refresh it from the DB.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    plan = FollowupPlan(
        id=str(uuid4()),
        patient_id=body.patient_id,
        consultation_id=body.consultation_id,
        created_by_user_id=clinician.id,
        instructions=body.instructions,
        created_at=now,
    )
    session.add(plan)

    await enroll_plan(session, plan)
    await session.commit()
    return _plan_out(plan)


@router.post("/{plan_id}/cancel")
async def cancel_followup_plan(
    plan_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    plan = await session.get(FollowupPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Follow-up plan not found")
    if plan.status != "active":
        raise HTTPException(status_code=409, detail=f"Plan is already {plan.status}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    plan.status = "cancelled"
    plan.completed_at = now

    active_workflow = await session.scalar(
        select(Workflow).where(Workflow.followup_plan_id == plan.id, Workflow.status == "active")
    )
    if active_workflow is not None:
        await cancel_workflow(session, active_workflow, now)

    await session.commit()
    return _plan_out(plan)


__all__ = ["router"]
