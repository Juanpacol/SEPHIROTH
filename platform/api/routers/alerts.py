"""Alert lifecycle (SPEC-011) -- the mutation surface `Alert` previously
lacked: `dashboard.py` only ever reads it. `review` and `resolve` are two
verbs, not a single `PATCH {status}`, because `resolve` must require a
prior `reviewed_at` -- `dashboard.py::_dashboard_alerts` computes
`avg_alert_response_seconds` as `reviewed_at - created_at`, and a
skip-straight-to-resolved alert would leave that None, breaking the
metric's numerator.

Resolving an alert also cancels any still-active `alert_escalation`
workflow anchored to it (`Workflow.alert_id`) -- a resolved alert has
nothing left to escalate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.db import get_session
from data.schemas import Alert, User, Workflow

from ..workflows.instantiate import cancel_workflow

router = APIRouter()


def _alert_out(alert: Alert) -> Dict[str, Any]:
    return {
        "id": alert.id,
        "patient_id": alert.patient_id,
        "category": alert.category,
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "detail": alert.detail,
        "source": alert.source,
        "assigned_to_user_id": alert.assigned_to_user_id,
        "due_at": alert.due_at.isoformat() if alert.due_at else None,
        "reviewed_at": alert.reviewed_at.isoformat() if alert.reviewed_at else None,
        "reviewed_by": alert.reviewed_by,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "escalated_at": alert.escalated_at.isoformat() if alert.escalated_at else None,
        "created_at": alert.created_at.isoformat(),
    }


@router.get("")
async def list_alerts(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = None,
    patient_id: Optional[str] = None,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Alert.status == status_filter)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if patient_id is not None:
        stmt = stmt.where(Alert.patient_id == patient_id)
    alerts = (await session.scalars(stmt)).all()
    return [_alert_out(a) for a in alerts]


async def _get_alert(session: AsyncSession, alert_id: str) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/review")
async def review_alert(
    alert_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    alert = await _get_alert(session, alert_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert.status = "reviewed"
    alert.reviewed_at = now
    alert.reviewed_by = clinician.id
    await session.commit()
    return _alert_out(alert)


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    alert = await _get_alert(session, alert_id)
    if alert.reviewed_at is None:
        raise HTTPException(status_code=409, detail="Alert must be reviewed before it can be resolved")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert.status = "resolved"
    alert.resolved_at = now

    active_workflows = (
        await session.scalars(
            select(Workflow).where(Workflow.alert_id == alert.id, Workflow.status == "active")
        )
    ).all()
    for wf in active_workflows:
        await cancel_workflow(session, wf, now)

    await session.commit()
    return _alert_out(alert)


__all__ = ["router"]
