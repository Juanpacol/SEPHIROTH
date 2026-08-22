"""Event catalog (SPEC-010) -- named things that happened, recorded as a
durable outbox row (`WorkflowEvent`), not published to a broker. No
broker exists in this deployment and none is being added: 5-minute tick
latency is already accepted (SPEC-009), Render's free tier can't afford
a second service, and what "event-driven" actually buys clinically is a
queryable audit trail of *why* a workflow ran later -- a table gives
that for free.

`emit()` is called from inside an existing request handler's own
transaction, right where the domain change happens, so a rolled-back
booking can never leave a phantom event. `SUBSCRIBERS` is empty in this
phase -- later phases register a handler per event type (e.g. Phase 9's
`alert_escalation` workflow subscribing to `CLINICAL_ALERT`); until
then every event is dispatched to nothing and recorded as
`no_subscriber`, never silently dropped.

Unlike `policy.py`, this module DOES touch the DB (`emit`/`dispatch_pending`
take a session) -- it lives under `src/sephiroth/workflows/` rather than
`platform/api/workflows/` anyway, so `src/sephiroth/safety/alerts.py`
(already clinical logic living in `src/`, per existing precedent) can
call `emit()` without the clinical-app layer (`platform/`) importing
back into the runtime layer, which ADR-010 reserves the other way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import WorkflowEvent

# Reserved names -- not every one has a real emitter wired yet (see
# events flagged below); reserving the name now means a later phase adds
# a subscriber + call site without inventing a new catalog entry.
NEW_APPOINTMENT = "NEW_APPOINTMENT"
MISSED_APPOINTMENT = "MISSED_APPOINTMENT"
LAB_RESULT_AVAILABLE = "LAB_RESULT_AVAILABLE"
CLINICAL_ALERT = "CLINICAL_ALERT"
PATIENT_MESSAGE = "PATIENT_MESSAGE"  # no patient-messaging feature exists yet -- unwired
FOLLOWUP_DUE = "FOLLOWUP_DUE"  # no follow-up plans exist yet (Phase 12) -- unwired

EventHandler = Callable[[AsyncSession, WorkflowEvent], Awaitable[None]]
SUBSCRIBERS: Dict[str, List[EventHandler]] = {}


def emit(
    session: AsyncSession,
    event_type: str,
    entity_type: str,
    entity_id: str,
    *,
    patient_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> WorkflowEvent:
    """Stages a `WorkflowEvent` row in the caller's own transaction.
    Does NOT commit -- same discipline as `_notify`
    (`platform/api/routers/scheduling.py`); the caller's existing commit
    covers it."""
    event = WorkflowEvent(
        id=str(uuid4()),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        patient_id=patient_id,
        payload=payload or {},
    )
    session.add(event)
    return event


async def dispatch_pending(session: AsyncSession, batch_size: int = 50) -> int:
    """Runs every registered subscriber for each `pending` event, oldest
    first, and marks it `dispatched` (>=1 subscriber ran) or
    `no_subscriber`. Called from the tick (SPEC-009) so recording an
    event and having something act on it stay decoupled -- a phase that
    adds a subscriber needs no change to any emitter call site. Returns
    the number of rows processed."""
    events = (
        await session.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.status == "pending")
            .order_by(WorkflowEvent.created_at)
            .limit(batch_size)
        )
    ).all()

    processed = 0
    for event in events:
        handlers = SUBSCRIBERS.get(event.event_type, [])
        for handler in handlers:
            await handler(session, event)
        if handlers:
            event.status = "dispatched"
            event.dispatched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            event.status = "no_subscriber"
        processed += 1

    if processed:
        await session.commit()
    return processed


__all__ = [
    "NEW_APPOINTMENT",
    "MISSED_APPOINTMENT",
    "LAB_RESULT_AVAILABLE",
    "CLINICAL_ALERT",
    "PATIENT_MESSAGE",
    "FOLLOWUP_DUE",
    "SUBSCRIBERS",
    "emit",
    "dispatch_pending",
]
