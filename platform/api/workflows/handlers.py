"""Step handlers -- DB reads/writes allowed, but a handler never commits
(the tick engine owns the transaction, same discipline as `_notify` in
`platform/api/routers/scheduling.py`) and must be safe to re-run.
"""

from __future__ import annotations

from data.schemas import Patient
from sephiroth.safety.alerts import generate_alerts_for_patient

from .registry import StepContext, StepResult


async def alert_refresh(ctx: StepContext) -> StepResult:
    """Proof-of-life step type for the workflow substrate (SPEC-009).

    `generate_alerts_for_all_patients` is otherwise only ever called from
    `init_db()` at boot (`platform/core/db.py`) -- clinical alerts go
    stale between deploys. This re-runs the same, already-idempotent
    per-patient logic (`src/sephiroth/safety/alerts.py::generate_alerts_for_patient`,
    which dedupes on `(category, title)` against open alerts) on a
    tick-driven cadence instead, fixing that real gap while introducing
    zero new domain logic.
    """
    patient = await ctx.session.get(Patient, ctx.workflow.patient_id)
    if patient is None:
        return StepResult(outcome="superseded", detail="patient no longer exists")

    created = await generate_alerts_for_patient(ctx.session, patient)
    return StepResult(outcome="succeeded", detail=f"{len(created)} new alert(s)", data={"created": len(created)})


__all__ = ["alert_refresh"]
