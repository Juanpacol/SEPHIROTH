"""Step handlers -- DB reads/writes allowed, but a handler never commits
(the tick engine owns the transaction, same discipline as `_notify` in
`platform/api/routers/scheduling.py`) and must be safe to re-run.
"""

from __future__ import annotations

from datetime import timedelta

from data.schemas import Patient
from sephiroth.safety.alerts import generate_alerts_for_patient
from sephiroth.workflows.policy import jittered

from .registry import StepContext, StepResult, StepTypeSpec, register_step_type

#: How often a patient's alerts are re-derived. Six hours because the inputs
#: (labs, medications) change on a clinical cadence, not a machine one.
ALERT_REFRESH_INTERVAL = timedelta(hours=6)


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

    # `deferred`, not `succeeded` (SPEC-020). Returning success here meant no
    # steps remained, the engine completed the parent workflow, and nothing
    # ever rescheduled it -- so "periodic" was aspirational and this ran
    # exactly once per patient, ever. Deferring keeps the workflow `active`
    # forever, which is the honest model for a standing job.
    #
    # Jittered because every patient is enrolled in one of these: without it
    # they all come due in the same tick forever, and a clinic with more
    # patients than `workflow_tick_batch_size` permanently starves the tail of
    # the list.
    return StepResult(
        outcome="deferred",
        detail=f"{len(created)} new alert(s); next sweep in ~6h",
        data={"created": len(created)},
        retry_at=ctx.now + jittered(ALERT_REFRESH_INTERVAL),
    )


register_step_type(
    StepTypeSpec(
        step_type="alert_refresh",
        handler=alert_refresh,
        max_attempts=3,
        max_lateness_seconds=None,  # internal housekeeping -- always worth catching up
        timeout_seconds=10.0,
        reads_phi=False,  # lab/med data already visible to any clinician; not a per-patient PHI read
        max_defers=None,  # a standing job defers forever by design
    )
)

__all__ = ["alert_refresh"]
