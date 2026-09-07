"""The visit's lifecycle, and everything signing sets in motion.

Signing is the only moment anything leaves the encounter: it writes the
`ClinicalNote` that reaches the chart. Before it, an encounter is invisible to
the rest of the product — which is what makes the signature, rather than a
separate approval row, the review gate for AI-drafted content (ADR-016).

Transaction discipline: **nothing here commits.** The routers commit.

Restoration note: signing an order used to also file a follow-up `Task`
(SPEC-018's unified inbox) via `task_service.create_task`. That system was
removed in the c7fbdf5 revert and is a later restoration phase — `_file_orders`
below is a deliberate no-op stub until it comes back, not a bug. See
`ORDER_TASK_CATEGORY`/`ORDER_TASK_SEVERITY`/`_ORDER_TITLE`, kept because
`add_order` still validates `kind` against them and Phase-3 wiring reuses them
verbatim.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import ClinicalNote, Encounter, EncounterOrder, User
from sephiroth.clinical.templates import render_note
from sephiroth.clinical.vitals import VitalError, validate_vitals

OPEN_STATUSES = ("draft", "amended")
NARRATIVE_FIELDS = ("chief_complaint", "subjective", "objective", "assessment", "plan")

#: Fields a `PATCH` may write. Everything else about an encounter is set by a
#: transition -- an allow-list rather than a deny-list, so a column added later
#: is not writable by accident.
EDITABLE_FIELDS = frozenset(
    {
        "chief_complaint",
        "subjective",
        "objective",
        "assessment",
        "plan",
        "patient_instructions",
        "specialty",
        "vitals",
        "note_source",
        "note_model",
    }
)

#: An order's kind, and the task category it would become once the unified
#: task inbox (SPEC-018) is restored. Kept here so `add_order`'s validation and
#: the eventual Phase-3 wiring share one source of truth.
ORDER_TASK_CATEGORY = {
    "lab": "lab",
    "imaging": "imaging",
    "referral": "followup",
    "followup": "followup",
    "medication": "medication",
}

#: How urgent the resulting task would be. An order with a deadline carries its
#: own due date, so severity here is about how it would sort in a list, not
#: when it is due -- a referral is not more urgent than a lab, it is just less
#: routine.
ORDER_TASK_SEVERITY = {
    "lab": "medium",
    "imaging": "medium",
    "referral": "medium",
    "followup": "low",
    "medication": "high",
}

_ORDER_TITLE = {
    "lab": "Laboratorio pendiente",
    "imaging": "Imagen pendiente",
    "referral": "Remisión pendiente",
    "followup": "Control pendiente",
    "medication": "Cambio de medicación",
}


class EncounterTransitionError(RuntimeError):
    """A transition the encounter's current state forbids. Surfaces as 409."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_editable(encounter: Encounter) -> bool:
    return encounter.status in OPEN_STATUSES


def has_content(encounter: Encounter) -> bool:
    return any((getattr(encounter, field) or "").strip() for field in NARRATIVE_FIELDS)


async def create_encounter(
    session: AsyncSession,
    *,
    patient_id: str,
    clinician: User,
    appointment_id: Optional[str] = None,
    specialty: str = "general",
    chief_complaint: str = "",
    now: Optional[datetime] = None,
) -> Encounter:
    moment = now or _now()
    encounter = Encounter(
        id=str(uuid4()),
        patient_id=patient_id,
        clinician_id=clinician.id,
        appointment_id=appointment_id or None,
        specialty=specialty or "general",
        chief_complaint=chief_complaint,
        status="draft",
        started_at=moment,
        created_at=moment,
        updated_at=moment,
    )
    session.add(encounter)
    return encounter


def update_encounter(
    encounter: Encounter, changes: Dict[str, Any], *, now: Optional[datetime] = None
) -> Encounter:
    """Apply a partial edit. Raises on a signed encounter or an unknown field."""
    if not is_editable(encounter):
        raise EncounterTransitionError("a signed encounter cannot be edited; amend it instead")

    unknown = sorted(set(changes) - EDITABLE_FIELDS)
    if unknown:
        raise EncounterTransitionError(f"not editable: {', '.join(unknown)}")

    for field, value in changes.items():
        if field == "vitals":
            # Raises `VitalError` for an impossible reading. An *abnormal* one
            # is stored and flagged on read -- refusing 210/120 would refuse
            # the emergency (SPEC-023 B-8).
            value = validate_vitals(value or {})
        setattr(encounter, field, value)
    encounter.updated_at = now or _now()
    return encounter


async def list_orders(session: AsyncSession, encounter: Encounter) -> List[EncounterOrder]:
    """The encounter's orders, always fetched explicitly.

    The relationship exists for the schema's sake, but nothing here reads it:
    touching a lazy collection on a flushed instance issues IO from wherever it
    happens to be touched, which under asyncio is a `MissingGreenlet` in a
    place that has nothing to do with orders. One query, at a point that is
    already awaiting, is easier to reason about than a loading strategy that
    has to hold everywhere.
    """
    return list(
        (
            await session.scalars(
                select(EncounterOrder)
                .where(EncounterOrder.encounter_id == encounter.id)
                .order_by(EncounterOrder.created_at)
            )
        ).all()
    )


async def add_order(
    session: AsyncSession,
    encounter: Encounter,
    *,
    kind: str,
    detail: str,
    due_in_days: Optional[int] = None,
    now: Optional[datetime] = None,
) -> EncounterOrder:
    if not is_editable(encounter):
        raise EncounterTransitionError("a signed encounter cannot take new orders; amend it first")
    if not (detail or "").strip():
        raise EncounterTransitionError("an order needs a detail")
    if kind not in ORDER_TASK_CATEGORY:
        raise EncounterTransitionError(f"unknown order kind: {kind}")
    if due_in_days is not None and due_in_days <= 0:
        raise EncounterTransitionError("due_in_days must be positive")

    order = EncounterOrder(
        id=str(uuid4()),
        encounter_id=encounter.id,
        kind=kind,
        detail=detail.strip(),
        due_in_days=due_in_days,
        created_at=now or _now(),
    )
    session.add(order)
    await session.flush()
    return order


async def remove_order(session: AsyncSession, encounter: Encounter, order: EncounterOrder) -> None:
    if not is_editable(encounter):
        raise EncounterTransitionError("a signed encounter's orders cannot be removed")
    if order.task_id is not None:
        # Belt and braces: an order that already filed work is not a draft
        # decision any more, and deleting it here would orphan the task.
        raise EncounterTransitionError("this order has already been filed as a task")
    await session.delete(order)
    await session.flush()


def rendered_note(encounter: Encounter, orders: Sequence[EncounterOrder] = ()) -> str:
    return render_note(
        chief_complaint=encounter.chief_complaint or "",
        vitals=encounter.vitals or {},
        subjective=encounter.subjective or "",
        objective=encounter.objective or "",
        assessment=encounter.assessment or "",
        plan=encounter.plan or "",
        patient_instructions=encounter.patient_instructions or "",
        orders=[{"kind": o.kind, "detail": o.detail, "due_in_days": o.due_in_days} for o in orders],
    )


async def sign_encounter(
    session: AsyncSession,
    encounter: Encounter,
    *,
    signer: User,
    now: Optional[datetime] = None,
) -> Tuple[Encounter, List[str]]:
    """Commit the visit. Returns the encounter and the ids of tasks it filed.

    Idempotent (B-5): signing a signed encounter changes nothing and files
    nothing. That matters because signing is the one action a clinician might
    double-click, and the cost of getting it wrong is a duplicate note in a
    chart plus duplicate work in somebody's inbox.
    """
    moment = now or _now()

    if encounter.status == "signed":
        return encounter, []
    if not has_content(encounter):
        raise EncounterTransitionError("an encounter with nothing written cannot be signed")
    if signer.id != encounter.clinician_id:
        raise EncounterTransitionError("only the clinician who conducted the visit may sign it")

    orders = await list_orders(session, encounter)

    # The note carries the narrative as it stood at signing. An amendment
    # writes a new one rather than editing this, so what was first committed
    # survives (SPEC-023 NG-5).
    note = ClinicalNote(
        id=str(uuid4()),
        patient_id=encounter.patient_id,
        user_id=signer.id,
        note_type="encounter",
        content=rendered_note(encounter, orders),
        extracted_entities={},
        created_at=moment,
    )
    session.add(note)
    encounter.clinical_note_id = note.id

    task_ids = await _file_orders(session, encounter, orders, now=moment)

    encounter.status = "signed"
    encounter.signed_at = moment
    encounter.signed_by = signer.id
    encounter.updated_at = moment
    return encounter, task_ids


async def _file_orders(
    session: AsyncSession, encounter: Encounter, orders: Sequence[EncounterOrder], now: datetime
) -> List[str]:
    """Would file one task per order via the unified task inbox (SPEC-018).

    Deliberate no-op for now: that system was removed by the c7fbdf5 revert
    and is a later restoration phase (see this module's docstring). Orders are
    still recorded on the encounter and still block deletion once
    `task_id` is set by that later phase -- signing an encounter with orders
    today just leaves them unfiled rather than raising, so a clinician is
    never blocked from completing a visit because of a gap in an unrelated
    subsystem.
    """
    return []


async def amend_encounter(
    session: AsyncSession,
    encounter: Encounter,
    *,
    actor: User,
    reason: str,
    window_days: int,
    now: Optional[datetime] = None,
) -> Encounter:
    """Reopen a signed encounter for correction.

    There is no un-sign. A signed note is a clinical record, and the honest
    correction mechanism is one that says on its face that a correction
    happened.
    """
    moment = now or _now()
    if encounter.status == "draft":
        raise EncounterTransitionError("an unsigned encounter is already editable")
    if not (reason or "").strip():
        raise EncounterTransitionError("an amendment needs a reason")
    signed_at = encounter.signed_at or encounter.started_at
    if moment - signed_at > timedelta(days=window_days):
        raise EncounterTransitionError(f"the amendment window of {window_days} days has passed")

    encounter.status = "amended"
    encounter.amended_at = moment
    encounter.amendment_reason = reason.strip()[:300]
    encounter.updated_at = moment
    return encounter


async def get_encounter(session: AsyncSession, encounter_id: str) -> Optional[Encounter]:
    return await session.get(Encounter, encounter_id)


async def list_encounters(
    session: AsyncSession,
    *,
    patient_id: Optional[str] = None,
    clinician_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Encounter]:
    query = select(Encounter).order_by(Encounter.started_at.desc())
    if patient_id:
        query = query.where(Encounter.patient_id == patient_id)
    if clinician_id:
        query = query.where(Encounter.clinician_id == clinician_id)
    if status:
        query = query.where(Encounter.status == status)
    return list((await session.scalars(query.limit(min(limit, 200)).offset(offset))).all())


__all__ = [
    "EDITABLE_FIELDS",
    "NARRATIVE_FIELDS",
    "OPEN_STATUSES",
    "ORDER_TASK_CATEGORY",
    "ORDER_TASK_SEVERITY",
    "EncounterTransitionError",
    "VitalError",
    "add_order",
    "amend_encounter",
    "create_encounter",
    "get_encounter",
    "has_content",
    "is_editable",
    "list_encounters",
    "list_orders",
    "remove_order",
    "rendered_note",
    "sign_encounter",
    "update_encounter",
]
