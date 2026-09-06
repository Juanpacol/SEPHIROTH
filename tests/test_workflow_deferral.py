"""The `deferred` outcome, and the two defects it made fixable.

A deferral is a decision, not a failure. Everything here is about keeping that
distinction real rather than merely stated: it must not consume a retry, it
must not complete the parent workflow, and it must be bounded so a
misconfiguration cannot silently defer forever — a notification that never
sends and never errors is the worst of both.

Verifies AC-020-01, AC-020-02, AC-020-03, AC-020-06, AC-020-12
(docs/specs/SPEC-020-automation-correctness.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.workflows import registry as registry_module
from api.workflows.engine import MIN_DEFER_SECONDS, claim_step, execute_step
from api.workflows.registry import StepResult, StepTypeSpec
from data.schemas import Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 12, 0, 0)


@pytest.fixture
def deferring_type(monkeypatch):
    """A step type that always defers, with an injectable answer."""
    plan = {"retry_at": NOW + timedelta(hours=6), "extend_lateness": False, "max_defers": 3}

    async def handler(ctx):
        return StepResult(
            outcome="deferred",
            detail="not now",
            retry_at=plan["retry_at"],
            extend_lateness=plan["extend_lateness"],
        )

    def register():
        monkeypatch.setitem(
            registry_module.STEP_TYPES,
            "test_defer",
            StepTypeSpec(
                step_type="test_defer",
                handler=handler,
                max_attempts=3,
                max_lateness_seconds=3600,
                reads_phi=False,
                max_defers=plan["max_defers"],
            ),
        )

    register()
    plan["reregister"] = register
    return plan


async def _step(session, *, due_at=NOW, step_type="test_defer", max_attempts=3):
    patient = Patient(
        id=f"PD{uuid4().hex[:6]}", name="Defer", age=40, sex="M", medical_record_number=str(uuid4())[:18]
    )
    session.add(patient)
    workflow = Workflow(
        id=str(uuid4()), definition_key="test", patient_id=patient.id, status="active", context={}
    )
    session.add(workflow)
    step = WorkflowStep(
        id=str(uuid4()),
        workflow_id=workflow.id,
        step_key="s1",
        step_type=step_type,
        status="pending",
        due_at=due_at,
        run_after=due_at,
        # The row carries its own budget; the spec's value is only the default
        # applied at enrolment, so a test has to set it here to mean it.
        max_attempts=max_attempts,
    )
    session.add(step)
    await session.commit()
    return step, workflow


async def _run(session, step, now=NOW):
    await claim_step(session, step.id, "tick", now, lease_seconds=120)
    return await execute_step(session, step.id, now)


class TestDeferralSemantics:
    async def test_a_deferred_step_goes_back_to_pending_with_a_new_time(self, db_session, deferring_type):
        step, _ = await _step(db_session)

        outcome = await _run(db_session, step)

        await db_session.refresh(step)
        assert outcome == "deferred"
        assert step.status == "pending"
        assert step.run_after == NOW + timedelta(hours=6)
        assert step.deferred_count == 1

    async def test_a_deferral_does_not_consume_a_retry(self, db_session, deferring_type):
        """Otherwise three quiet nights in a row permanently kill a reminder."""
        step, _ = await _step(db_session)

        for _ in range(3):
            await _run(db_session, step)
            await db_session.refresh(step)

        assert step.attempts == 0
        assert step.deferred_count == 3
        assert step.status == "pending"

    async def test_a_deferred_step_does_not_complete_its_workflow(self, db_session, deferring_type):
        """This is what made `alert_refresh` run exactly once, ever: succeeding
        left no steps pending, so the engine completed the parent."""
        step, workflow = await _step(db_session)

        await _run(db_session, step)

        await db_session.refresh(workflow)
        assert workflow.status == "active"

    async def test_a_handler_asking_for_now_is_floored(self, db_session, deferring_type):
        """A step that asks to be reconsidered immediately would be re-claimed
        by the same tick's remaining budget and spin."""
        deferring_type["retry_at"] = NOW
        deferring_type["reregister"]()
        step, _ = await _step(db_session)

        await _run(db_session, step)

        await db_session.refresh(step)
        assert step.run_after >= NOW + timedelta(seconds=MIN_DEFER_SECONDS)

    async def test_deferring_past_the_limit_fails_loudly(self, db_session, deferring_type):
        """An unbounded defer loop is invisible: nothing errors, nothing sends."""
        deferring_type["max_defers"] = 2
        deferring_type["reregister"]()
        step, _ = await _step(db_session)

        outcomes = []
        for _ in range(3):
            outcomes.append(await _run(db_session, step))
            await db_session.refresh(step)

        assert outcomes == ["deferred", "deferred", "failed"]
        assert step.status == "failed"
        assert "defer limit" in step.last_error

    async def test_a_standing_job_may_defer_without_limit(self, db_session, deferring_type):
        deferring_type["max_defers"] = None
        deferring_type["reregister"]()
        step, _ = await _step(db_session)

        for _ in range(6):
            outcome = await _run(db_session, step)
            await db_session.refresh(step)

        assert outcome == "deferred"
        assert step.status == "pending"


class TestLatenessBudget:
    async def test_the_per_row_budget_is_what_the_engine_reads(self, db_session, deferring_type):
        """`on_new_appointment` and `enroll_plan` populate this column per step
        and the engine read only the step *type*'s value, so it was dead."""
        step, _ = await _step(db_session, due_at=NOW - timedelta(hours=10))
        step.max_lateness_seconds = 60  # far tighter than the type's 3600
        await db_session.commit()

        outcome = await _run(db_session, step)

        assert outcome == "skipped"

    async def test_extend_lateness_widens_only_this_row(self, db_session, deferring_type):
        """A reminder due at 23:00 and deferred to 08:00 would otherwise blow
        past its window and be silently skipped — the deferral would look like
        it worked and nothing would arrive."""
        deferring_type["extend_lateness"] = True
        deferring_type["retry_at"] = NOW + timedelta(hours=9)
        deferring_type["reregister"]()
        step, _ = await _step(db_session)

        await _run(db_session, step)
        await db_session.refresh(step)
        widened = step.max_lateness_seconds

        # Wide enough to cover the wait it just asked for...
        assert widened is not None and widened >= 9 * 3600
        # ...and the step type is untouched for everyone else.
        assert registry_module.STEP_TYPES["test_defer"].max_lateness_seconds == 3600

        # And it actually runs when it wakes up, rather than being skipped.
        step.run_after = NOW + timedelta(hours=9)
        await db_session.commit()
        assert await _run(db_session, step, now=NOW + timedelta(hours=9)) == "deferred"


class TestFailedStepsBecomeWork:
    async def test_a_terminally_failed_step_files_a_task(self, db_session, monkeypatch):
        """A counter on a page nobody opens is not how anyone finds out that a
        patient's reminder never went."""
        from data.schemas import Task

        async def boom(ctx):
            raise RuntimeError("channel unreachable")

        monkeypatch.setitem(
            registry_module.STEP_TYPES,
            "test_boom",
            StepTypeSpec(step_type="test_boom", handler=boom, max_attempts=1, reads_phi=False),
        )
        step, _ = await _step(db_session, step_type="test_boom", max_attempts=1)

        assert await _run(db_session, step) == "failed"

        tasks = (await db_session.scalars(select(Task).where(Task.source_type == "automation"))).all()
        assert len(tasks) == 1
        assert tasks[0].source_id == step.id
        assert "channel unreachable" in tasks[0].detail

    async def test_a_step_that_retries_files_nothing(self, db_session, monkeypatch):
        """Only terminal exhaustion is work for a person."""
        from data.schemas import Task

        async def boom(ctx):
            raise RuntimeError("transient")

        monkeypatch.setitem(
            registry_module.STEP_TYPES,
            "test_retry",
            StepTypeSpec(step_type="test_retry", handler=boom, max_attempts=3, reads_phi=False),
        )
        step, _ = await _step(db_session, step_type="test_retry")

        await _run(db_session, step)

        assert (await db_session.scalars(select(Task))).all() == []
