"""Engine-level tests against SQLite in-memory (`db_session`) — the same
claim-CAS SQL path runs against Postgres in production; see SPEC-009 for
why no dialect branch exists."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.workflows import registry as registry_module
from api.workflows.engine import claim_step, execute_step, reclaim_expired_leases, run_tick
from api.workflows.registry import StepContext, StepResult, StepTypeSpec
from data.schemas import Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 21, 12, 0, 0)


async def _patient(session, pid="PWF1"):
    p = Patient(id=pid, name="Workflow Patient", age=40, sex="F", medical_record_number=f"PT-{pid}")
    session.add(p)
    await session.commit()
    return p


async def _workflow(session, patient_id, definition_key="test_def"):
    wf = Workflow(id=str(uuid4()), definition_key=definition_key, patient_id=patient_id, status="active")
    session.add(wf)
    await session.commit()
    return wf


async def _step(session, workflow_id, step_type, *, status="pending", due_at=NOW, run_after=None,
                 attempts=0, max_attempts=3, lease_expires_at=None, claimed_by=""):
    step = WorkflowStep(
        id=str(uuid4()),
        workflow_id=workflow_id,
        step_key=str(uuid4())[:8],
        step_type=step_type,
        status=status,
        due_at=due_at,
        run_after=run_after or due_at,
        attempts=attempts,
        max_attempts=max_attempts,
        lease_expires_at=lease_expires_at,
        claimed_by=claimed_by,
    )
    session.add(step)
    await session.commit()
    return step


async def test_claim_step_cas_race_only_one_winner(db_session):
    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(db_session, wf.id, "whatever")

    first = await claim_step(db_session, step.id, "tick-a", NOW, lease_seconds=120)
    second = await claim_step(db_session, step.id, "tick-b", NOW, lease_seconds=120)

    assert first is True
    assert second is False
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert refreshed.status == "running"
    assert refreshed.claimed_by == "tick-a"
    assert refreshed.attempts == 1


async def test_reclaim_expired_leases_returns_step_to_pending(db_session):
    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(
        db_session,
        wf.id,
        "whatever",
        status="running",
        lease_expires_at=NOW - timedelta(seconds=1),
        claimed_by="stale-tick",
    )

    reclaimed = await reclaim_expired_leases(db_session, NOW)

    assert reclaimed == 1
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert refreshed.status == "pending"
    assert refreshed.claimed_by == ""


async def test_execute_step_missing_step_returns_error(db_session):
    outcome = await execute_step(db_session, "does-not-exist", NOW)
    assert outcome == "error"


async def test_execute_step_missing_workflow_fails(db_session):
    # SQLite (unlike Postgres) doesn't enforce the FK by default, so a
    # step can reference a workflow id that was never actually created --
    # exercised here directly rather than via a hard delete (workflows are
    # never hard-deleted in this codebase's real flows).
    step = await _step(db_session, "no-such-workflow", "whatever", status="running")

    outcome = await execute_step(db_session, step.id, NOW)

    assert outcome == "failed"
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert refreshed.status == "failed"
    assert "parent workflow not found" in refreshed.last_error


async def test_execute_step_unknown_type_fails_terminally(db_session):
    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(db_session, wf.id, "no_such_step_type", status="running")

    outcome = await execute_step(db_session, step.id, NOW)

    assert outcome == "failed"
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert refreshed.status == "failed"
    assert "no_such_step_type" in refreshed.last_error


async def test_execute_step_past_max_lateness_is_skipped(db_session, monkeypatch):
    async def _never_called(ctx: StepContext) -> StepResult:
        raise AssertionError("stale step must not run its handler")

    monkeypatch.setitem(
        registry_module.STEP_TYPES,
        "stale_test",
        StepTypeSpec(step_type="stale_test", handler=_never_called, max_lateness_seconds=3600),
    )

    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(
        db_session, wf.id, "stale_test", status="running", due_at=NOW - timedelta(hours=5)
    )

    outcome = await execute_step(db_session, step.id, NOW)

    assert outcome == "skipped"
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert refreshed.status == "skipped"


async def test_execute_step_retries_then_terminally_fails(db_session, monkeypatch):
    async def _always_raises(ctx: StepContext) -> StepResult:
        raise RuntimeError("transient boom")

    monkeypatch.setitem(
        registry_module.STEP_TYPES,
        "always_fails",
        StepTypeSpec(step_type="always_fails", handler=_always_raises, max_attempts=2),
    )

    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(db_session, wf.id, "always_fails", status="running", attempts=1, max_attempts=2)

    first_outcome = await execute_step(db_session, step.id, NOW)
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert first_outcome == "failed"  # this attempt failed...
    assert refreshed.status == "pending"  # ...but retried, attempts (1) < max_attempts (2)
    assert refreshed.failure_category == "tool"

    # Second attempt: claim bumps attempts to 2 == max_attempts -> terminal.
    await claim_step(db_session, step.id, "tick-2", NOW, lease_seconds=120)
    second_outcome = await execute_step(db_session, step.id, NOW)
    refreshed = await db_session.get(WorkflowStep, step.id)
    assert second_outcome == "failed"
    assert refreshed.status == "failed"


async def test_execute_step_success_completes_workflow_when_no_steps_remain(db_session, monkeypatch):
    async def _succeeds(ctx: StepContext) -> StepResult:
        return StepResult(outcome="succeeded", data={"ok": True})

    monkeypatch.setitem(
        registry_module.STEP_TYPES,
        "succeeds_test",
        StepTypeSpec(step_type="succeeds_test", handler=_succeeds),
    )

    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    step = await _step(db_session, wf.id, "succeeds_test", status="running")

    outcome = await execute_step(db_session, step.id, NOW)

    assert outcome == "succeeded"
    refreshed_wf = await db_session.get(Workflow, wf.id)
    assert refreshed_wf.status == "completed"
    assert refreshed_wf.completed_at == NOW


async def test_run_tick_respects_batch_size_and_reports_remaining(db_session, monkeypatch):
    async def _succeeds(ctx: StepContext) -> StepResult:
        return StepResult(outcome="succeeded")

    monkeypatch.setitem(
        registry_module.STEP_TYPES,
        "batch_test",
        StepTypeSpec(step_type="batch_test", handler=_succeeds),
    )
    from core.config import settings

    monkeypatch.setattr(settings, "workflow_tick_batch_size", 1)

    real_now = datetime.now(timezone.utc).replace(tzinfo=None)  # run_tick computes its own "now"
    patient = await _patient(db_session)
    wf = await _workflow(db_session, patient.id)
    await _step(db_session, wf.id, "batch_test", due_at=real_now - timedelta(minutes=5))
    await _step(db_session, wf.id, "batch_test", due_at=real_now - timedelta(minutes=3))

    summary = await run_tick(db_session, tick_id="test-tick")

    assert summary.claimed == 1
    assert summary.succeeded == 1
    assert summary.remaining == 1
