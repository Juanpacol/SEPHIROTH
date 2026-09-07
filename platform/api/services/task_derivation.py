"""Work nobody filed: conditions that are only visible by looking.

Five of the eight kinds of work on a clinician's list have no row that says
"do this" — a lab trend that is worsening, a drug pair that interacts, an
imaging study nobody has opened, a follow-up that slipped, a high-risk
consultation left unacted-on. `dashboard.py` found them by re-running the same
queries on every page load and returning them as text.

Persisting them buys the things a derived list cannot have: an assignee, a due
date, a snooze, a comment, a history. It costs the thing a derived list had for
free — when the condition goes away, the row does not. So this module owns both
halves: it creates the task, and it supersedes the task when the condition
behind it stops holding. A persisted inbox without the second half is worse
than the derived list it replaced, because it accumulates.

`dedupe_key` is what makes running this every five minutes safe. It is keyed on
the *condition*, not on the sweep: the same worsening trend produces the same
key forever, so the second tick finds the task it made on the first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import (
    Consultation,
    ImagingStudy,
    LabResult,
    Patient,
    PendingAction,
    Task,
    Workflow,
    WorkflowStep,
)

from . import task_service as svc

#: Source types whose tasks this module owns end to end. A task of any other
#: type is somebody else's to create and to close, and the sweep must not
#: touch it — superseding an alert task because no rule re-derived it would
#: silently close real work.
DERIVED_SOURCE_TYPES = ("deteriorating", "interaction", "result", "consultation")

#: How many rows of one category the *dashboard* shows. It is deliberately NOT
#: applied to derivation.
#:
#: It used to be, copied from `dashboard.py` where it caps a display list. That
#: is a different thing from capping what exists: the sweep supersedes any open
#: derived task whose condition is absent from the current pass, so a ninth
#: critical lab silently and permanently destroyed the eighth -- `create_task`
#: never revives a superseded key, so an unreviewed critical result left the
#: inbox and could not come back. A clinician cannot see a cap; they only see
#: work disappear.
#:
#: Derivation now yields every condition that is currently true. The bound is
#: the clinical reality: if fifty patients have a critical potassium, fifty
#: tasks is the correct answer.
DISPLAY_LIMIT_PER_CATEGORY = 8


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _interaction_key(patient_id: str, drug_a: str, drug_b: str) -> str:
    # Sorted, so "warfarin + aspirin" and "aspirin + warfarin" are one finding
    # rather than two tasks for the same clinical fact.
    a, b = sorted([drug_a.strip().lower(), drug_b.strip().lower()])
    return f"derived:interaction:{patient_id}:{a}|{b}"


async def _patient_names(session: AsyncSession) -> Dict[str, str]:
    rows = (await session.execute(select(Patient.id, Patient.name))).all()
    return {pid: name for pid, name in rows}


async def _deteriorating(session: AsyncSession, names: Dict[str, str]) -> List[Dict[str, Any]]:
    # Imported here, not at module scope: dashboard.py imports this module's
    # siblings, and a top-level import would close the cycle.
    from api.clinical.routers.dashboard import _evolution_deteriorating

    entries, _ = await _evolution_deteriorating(session)
    out = []
    for entry in entries:
        out.append(
            {
                "dedupe_key": f"derived:deteriorating:{entry['id']}",
                "source_type": "deteriorating",
                "source_id": entry["id"],
                "category": "deteriorating",
                "severity": "high",
                "patient_id": entry["id"],
                "title": f"{entry['name']}: empeorando",
                "context": {"patient_name": entry["name"]},
            }
        )
    return out


async def _critical_labs(session: AsyncSession, names: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = (await session.scalars(select(LabResult).order_by(LabResult.taken_at))).all()
    latest: Dict[Tuple[str, str], LabResult] = {}
    for r in rows:
        latest[(r.patient_id, r.test_name)] = r
    critical = [r for r in latest.values() if r.is_critical]
    critical.sort(key=lambda r: r.taken_at, reverse=True)

    return [
        {
            # Keyed on the measurement, so a *new* critical value is new work
            # rather than an update to the old task.
            "dedupe_key": f"derived:lab:{r.id}",
            "source_type": "result",
            "source_id": str(r.id),
            "category": "lab",
            "severity": "critical",
            "patient_id": r.patient_id,
            "title": f"{r.test_name} crítico: {r.value} {r.unit}".strip(),
            "context": {"test_name": r.test_name, "value": r.value, "unit": r.unit},
        }
        for r in critical
    ]


async def _interactions(session: AsyncSession) -> List[Dict[str, Any]]:
    from intelligence.mcp.drug_safety_server import find_interactions

    patients = (await session.scalars(select(Patient).where(Patient.status == "active"))).all()
    out: List[Dict[str, Any]] = []
    for p in patients:
        if len(p.medications) < 2:
            continue
        for hit in find_interactions(p.medications):
            drug_a, drug_b = hit["pair"]
            out.append(
                {
                    "dedupe_key": _interaction_key(p.id, drug_a, drug_b),
                    "source_type": "interaction",
                    "source_id": p.id,
                    "category": "interaction",
                    "severity": "high" if hit.get("severity") == "major" else "medium",
                    "patient_id": p.id,
                    "title": f"Interacción posible: {drug_a} + {drug_b}",
                    "context": {"drug_a": drug_a, "drug_b": drug_b, "severity": hit.get("severity")},
                }
            )
    return out


async def _imaging(session: AsyncSession) -> List[Dict[str, Any]]:
    studies = (
        await session.scalars(
            select(ImagingStudy)
            .where(ImagingStudy.severity.in_(("critical", "review")))
            .order_by(ImagingStudy.study_date.desc())
        )
    ).all()
    return [
        {
            "dedupe_key": f"derived:imaging:{s.id}",
            "source_type": "result",
            "source_id": str(s.id),
            "category": "imaging",
            "severity": "critical" if s.severity == "critical" else "medium",
            "patient_id": s.patient_id,
            "title": f"Revisar {s.modality} de {s.body_part}",
            "context": {"modality": s.modality, "body_part": s.body_part},
        }
        for s in studies
    ]


async def _unacted_high_risk(session: AsyncSession) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            select(Consultation.id, Consultation.patient_id, Consultation.query)
            .where(Consultation.acted_on.is_(None), Consultation.risk_level == "high")
            .order_by(Consultation.id.desc())
        )
    ).all()
    out = []
    for c in rows:
        preview = c.query if len(c.query) <= 140 else c.query[:137] + "…"
        out.append(
            {
                "dedupe_key": f"derived:decision:{c.id}",
                "source_type": "consultation",
                "source_id": str(c.id),
                "category": "decision",
                "severity": "high",
                "patient_id": c.patient_id,
                "title": "Consulta de alto riesgo sin resolver",
                "context": {"consultation_id": c.id, "query_preview": preview},
            }
        )
    return out


async def _overdue_followups(session: AsyncSession, now: datetime) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            select(WorkflowStep, Workflow)
            .join(Workflow, WorkflowStep.workflow_id == Workflow.id)
            .where(
                WorkflowStep.step_type == "followup_check_due",
                WorkflowStep.status == "pending",
                WorkflowStep.due_at < now,
                Workflow.followup_plan_id.isnot(None),
            )
            .order_by(WorkflowStep.due_at)
        )
    ).all()
    return [
        {
            "dedupe_key": f"followup:{step.id}",
            "source_type": "followup",
            # Points at the plan, not the step, so the followup adapter can ask
            # whether the plan was cancelled.
            "source_id": workflow.followup_plan_id,
            "category": "followup",
            "severity": "medium",
            "patient_id": workflow.patient_id,
            "title": f"Seguimiento {step.step_key} vencido",
            "context": {"check_key": step.step_key, "days_late": max((now - step.due_at).days, 0)},
        }
        for step, workflow in rows
    ]


async def _pending_approvals(session: AsyncSession) -> List[Dict[str, Any]]:
    rows = (
        await session.scalars(
            select(PendingAction).where(PendingAction.status == "pending").order_by(PendingAction.created_at)
        )
    ).all()
    return [
        {
            "dedupe_key": f"approval:{pa.id}",
            "source_type": "approval",
            "source_id": pa.id,
            "category": "approval",
            "severity": "medium",
            "patient_id": pa.patient_id,
            "title": "Mensaje al paciente esperando aprobación",
            "context": {"action_type": pa.action_type},
            "source_deadline": pa.expires_at,
        }
        for pa in rows
    ]


async def sync_derived_tasks(session: AsyncSession, now: datetime | None = None) -> Dict[str, int]:
    """Bring the task table in line with what is true right now.

    Returns `{"created": n, "superseded": m}`. Runs from the tick.
    """
    moment = now or _now()
    names = await _patient_names(session)

    specs: List[Dict[str, Any]] = []
    specs += await _deteriorating(session, names)
    specs += await _critical_labs(session, names)
    specs += await _interactions(session)
    specs += await _imaging(session)
    specs += await _unacted_high_risk(session)
    specs += await _overdue_followups(session, moment)
    specs += await _pending_approvals(session)

    created = 0
    for spec in specs:
        _, was_created = await svc.create_task(session, now=moment, **spec)
        created += 1 if was_created else 0

    # Retire what is no longer true. Scoped to the source types this module
    # owns end to end (see DERIVED_SOURCE_TYPES) — a task type someone else
    # creates would otherwise be closed simply because no rule here re-derived
    # it.
    live_keys: Set[str] = {s["dedupe_key"] for s in specs}
    stale = (
        await session.scalars(
            select(Task).where(
                Task.status.in_(svc.OPEN_STATUSES),
                Task.source_type.in_(DERIVED_SOURCE_TYPES),
                Task.dedupe_key.not_in(live_keys) if live_keys else Task.id.is_not(None),
            )
        )
    ).all()

    superseded = 0
    for task in stale:
        await svc.transition(
            session,
            task,
            "supersede",
            actor=None,
            now=moment,
            note="the condition behind this task no longer holds",
        )
        superseded += 1

    return {"created": created, "superseded": superseded}


__all__ = ["sync_derived_tasks", "DERIVED_SOURCE_TYPES", "DISPLAY_LIMIT_PER_CATEGORY"]
