---
id: SPEC-020
title: Automation Correctness
phase: 18
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-009, SPEC-018]
adrs: []
features: [F-085, F-086, F-087, F-088]
diagrams: []
---

# SPEC-020 — Automation Correctness

## 1. Summary

Closes the defects SPEC-009 §11 recorded, and the deferral gap that made three
of them unfixable. The engine gains a `deferred` outcome — "not now, ask me
again at T" — and with it `quiet_hours` and `reminder_lead_hours` finally do
something, `alert_refresh` becomes genuinely periodic, no-shows are detected,
a reschedule keeps its reminder, a failed automation becomes visible work, and
an approval never shows a blank draft.

## 2. Motivation

Six things were wrong, and they were not independent:

1. **`execute_step` ignored `WorkflowStep.max_lateness_seconds`**
   (`engine.py:128` before this phase). It read the step *type*'s value, so the
   per-row column that `on_new_appointment` and `enroll_plan` carefully
   populate was dead.
2. **`alert_refresh` ran exactly once, ever.** It returned `succeeded`, no
   steps remained, `execute_step` completed the parent workflow, and nothing
   rescheduled it. "Periodic" was aspirational.
3. **Rescheduling an appointment silently lost its reminder.**
   `_load_live_appointment` compares `start_at` against the workflow's
   snapshot and correctly returns `superseded`, so nothing fired against stale
   data — but the workflow stayed `active`, `on_new_appointment`'s idempotency
   guard would then refuse a replacement, and no event was emitted anyway.
4. **`quiet_hours` and `reminder_lead_hours` were read by nothing.**
   `workflows/memory.py`'s own docstring named the blocker exactly: honouring
   them needs a `StepResult` outcome meaning "not done, try again later", which
   the engine did not have.
5. **`MISSED_APPOINTMENT` had no producer**, and `Appointment.status`'s
   `no_show` value could only be set by a clinician remembering to — so the
   number measured annotation diligence.
6. **A follow-up created an empty draft.** `followup_check_due` wrote
   `draft_text=""` with `draft_source="llm"`, so the approvals inbox could show
   a row with nothing in it and a button asking the clinician to babysit the
   automation before reviewing its output.

## 3. Goals

- **G-1** A handler can decline to act now without failing or being retried.
- **G-2** Stored automation preferences change behaviour.
- **G-3** A standing job stays standing.
- **G-4** An appointment that has been and gone says so, on its own.
- **G-5** An automation that gave up reaches a person.
- **G-6** An approval row is never blank.

## 4. Non-Goals

- **NG-1** No worker process; the external 5-minute tick is unchanged.
- **NG-2** No LLM call from the tick. The follow-up draft is a deterministic
  template; upgrading it stays a request-path action.
- **NG-3** No multi-tier escalation ladder (still SPEC-009's single tier).
- **NG-4** Quiet hours do **not** apply to clinician-facing notifications. See
  B-5 — this is a safety decision, not an oversight.
- **NG-5** No jitter on retry backoff. Only the periodic interval gets it; see
  §11 risk 4.
- **NG-6** `PATIENT_MESSAGE` and `FOLLOWUP_DUE` remain unwired.

## 5. Definitions

- **Deferral** — a handler's decision that now is the wrong moment, carrying
  when to reconsider. Not a failure, not an attempt, never a stored status.
- **Grace period** — how long after an appointment ends before an untouched
  booking is called a no-show.

## 6. Contracts

### 6.1 Types

`platform/api/workflows/registry.py`:

```python
@dataclass(frozen=True)
class StepResult:
    outcome: Literal["succeeded", "skipped", "superseded", "deferred"]
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    retry_at: Optional[datetime] = None  # deferred only
    extend_lateness: bool = False  # deferred only


@dataclass(frozen=True)
class StepTypeSpec:
    ...
    max_defers: int | None = 50  # None = unlimited
```

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `WorkflowStep.deferred_count` | int | yes | 0 | counted apart from `attempts` |
| `StepResult.retry_at` | datetime | no | null | floored to `now + 60s` by the engine |
| `StepTypeSpec.max_defers` | int/None | no | 50 | `None` only for a standing job |

### 6.2 Interfaces

```python
# src/sephiroth/workflows/policy.py  (pure)
def jittered(delta: timedelta, rng: Random | None = None) -> timedelta
def quiet_window_end(now, start_hhmm, end_hhmm, tz) -> datetime | None

# src/sephiroth/workflows/templates.py  (pure)
def render_followup_draft(check_key, instructions="", first_name="") -> str

# platform/api/workflows/
async def defer_for_quiet_hours(session, now, *, patient_id, user_id) -> datetime | None
async def sweep_missed_appointments(session, now, limit=100) -> int
async def maybe_seed_alert_refresh(session) -> int
async def report_step_needs_attention(session, step, workflow, now) -> None
```

### 6.3 State machine

One transition added to SPEC-009 §6.3:

| From | Event | To | Guard |
|---|---|---|---|
| running | handler returns `deferred` | pending | `run_after = max(retry_at, now+60s)`; `attempts` decremented; `deferred_count` incremented |
| running | `deferred` past `max_defers` | failed | `max_defers is not None and deferred_count > max_defers` |

`deferred` is never written to `WorkflowStep.status`, so the status CHECK
constraint and `GET /api/dashboard/automation` are untouched.

### 6.4 Errors

No new exception types. `report_step_needs_attention` swallows and logs
everything: a failure in the reporting of a failure must not take down the tick
processing the rest of the batch.

### 6.5 Configuration

| Key | Type | Default | Rule |
|---|---|---|---|
| `clinic_timezone` | str | `America/Bogota` | IANA name; quiet hours are wall-clock. An unparseable value falls back to UTC rather than raising |
| `no_show_grace_hours` | int | 24 | generous on purpose — a clinician annotating yesterday's list should win |

## 7. Behaviour

- **B-1** A `deferred` step MUST return to `pending` with `run_after` at least
  60 seconds out, and MUST NOT consume an attempt.
- **B-2** A `deferred` step MUST NOT complete its parent workflow.
- **B-3** Deferring past `max_defers` MUST fail the step loudly.
- **B-4** `execute_step` MUST prefer the step row's `max_lateness_seconds` over
  the step type's, and `extend_lateness` MUST widen only that row.
- **B-5** Quiet hours MUST apply to patient-facing steps only. An alert
  escalation at 03:00 is exactly what escalation is for, and applying a
  comfort setting to it would let that setting silence an emergency.
- **B-6** `reminder_lead_hours` MUST be resolved at enrolment and recorded on
  the workflow; a preference that later becomes *shorter* MUST defer.
- **B-7** `alert_refresh` MUST defer rather than succeed, and its interval MUST
  be jittered.
- **B-8** Enrolment of new patients into alert refresh MUST happen without a
  manual step, at most once per calendar day.
- **B-9** A booking still `booked` past its grace period MUST become
  `no_show`, MUST emit `MISSED_APPOINTMENT` exactly once, and MUST cancel
  workflows anchored to it.
- **B-10** Rescheduling MUST cancel the old workflow and emit a fresh
  `NEW_APPOINTMENT`.
- **B-11** A step that exhausts its attempts MUST file a task; one that
  retries MUST NOT.
- **B-12** A `PendingAction` MUST NOT exist with an empty `draft_text`,
  enforced by a database constraint.
- **B-13** An unreachable model during a draft upgrade MUST leave the template
  in place and return 200, not 503.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-020-01 | A deferred step returns to `pending` with a later `run_after` and an unchanged attempt count | B-1 | `tests/test_workflow_deferral.py::TestDeferralSemantics` |
| AC-020-02 | A deferred step leaves its workflow `active` | B-2 | `tests/test_workflow_deferral.py::test_a_deferred_step_does_not_complete_its_workflow` |
| AC-020-03 | Deferring past the limit fails the step; a standing job may defer without limit | B-3 | `tests/test_workflow_deferral.py::TestDeferralSemantics` |
| AC-020-04 | A midnight-wrapping quiet window is computed correctly in local time | B-5 | `tests/test_quiet_hours.py::TestWindowArithmetic` |
| AC-020-05 | A patient's own window overrides the clinic's, in both directions | B-5 | `tests/test_quiet_hours.py::TestScopePrecedence` |
| AC-020-06 | The per-row lateness budget is what the engine reads, and `extend_lateness` widens only that row | B-4 | `tests/test_workflow_deferral.py::TestLatenessBudget` |
| AC-020-07 | A long-past booking becomes `no_show` and emits exactly one event; a recent one does not | B-9 | `tests/test_no_show_sweep.py::TestSweep` |
| AC-020-08 | Rescheduling cancels the old workflow and re-emits `NEW_APPOINTMENT` | B-10 | `tests/test_no_show_sweep.py::TestRescheduleReenrols` |
| AC-020-09 | A follow-up step creates a non-empty draft naming what the clinician asked to watch | B-12 | `tests/test_patient_followup_workflow.py::test_followup_check_due_creates_a_sendable_draft` |
| AC-020-10 | A template draft can be upgraded, and an unreachable model keeps the template rather than 503-ing | B-13 | `tests/test_approval_draft_endpoint.py` |
| AC-020-11 | `alert_refresh` re-arms itself and never completes its workflow | B-7 | `tests/test_workflow_alert_refresh.py::test_alert_refresh_handler_runs_twice_without_duplicating_alerts` |
| AC-020-12 | A terminally failed step files exactly one task; a retrying step files none | B-11 | `tests/test_workflow_deferral.py::TestFailedStepsBecomeWork` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | quiet-window arithmetic, jitter, draft template | `tests/test_quiet_hours.py` |
| Engine | deferral semantics, lateness budget, failure→task | `tests/test_workflow_deferral.py` |
| Definitions | periodic refresh, reminder lead time, quiet-hours deferral | `tests/test_workflow_alert_refresh.py`, `test_appointment_reminder_workflow.py` |
| Sweep | no-show detection, reschedule re-enrolment | `tests/test_no_show_sweep.py` |
| API | draft upgrade and its degradation | `tests/test_approval_draft_endpoint.py` |

## 10. Migration & Compatibility

Revision `c4f1a86d2e70`. Two additive changes (`workflow_steps.deferred_count`,
`ix_appointments_status_end`) and one that is **not** purely additive:
`ck_pending_action_draft_nonempty` would fail on any still-pending row created
by the old empty-draft path, so the migration backfills those rows first. The
backfill text is frozen in the revision rather than imported from
`sephiroth.workflows.templates` — a migration must not depend on application
code whose behaviour can change underneath a historical revision.

Written by hand: the local Postgres was unavailable when this landed, so the
statements were derived from the model diff rather than autogenerated.
`tests/test_alembic_migration.py` is the drift guard and self-skips without a
database — **so this revision has not been executed against a real Postgres
yet**, and doing so is the first item on the phase's verification list.

Behavioural changes that alter existing contracts, all deliberate:
`alert_refresh` returns `deferred` instead of `succeeded`; a follow-up's
`draft_source` is `template` instead of `llm`; `POST /{id}/draft` accepts a
template draft and no longer 503s when the model is down.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | The migration has not run against Postgres | Recorded above; first verification step. The backfill is the part to watch — a production row with a non-empty draft must not be rewritten, which is why the UPDATE is scoped to `draft_text = ''` |
| 2 | `reminder_lead_hours` resolved at enrolment does not re-anchor existing bookings | Accepted and asymmetric on purpose: reading it at execution time would make `due_at` meaningless and force every appointment to be woken constantly. Wanting *less* notice is handled by the execution-time deferral; wanting *more* on an appointment already inside the old window is not something rescheduling fixes anyway, and it self-corrects on the next booking |
| 3 | Quiet hours could silence something urgent | Bounded by B-5: patient-facing steps only. `alert_escalation` and `clinical_notify` deliberately never call the resolver |
| 4 | Jitter only on the periodic interval, not on retry backoff | Deliberate. At a 5-minute cron cadence the tick granularity dwarfs jitter on a 30-second base, and `batch_size` caps concurrency. The fan-out that is real is one standing step per patient, all landing in the same tick forever |
| 5 | `max_defers=50` is a guess | Accepted: it exists to make a misconfiguration visible, not to be precise. At the quiet-hours cadence 50 deferrals is weeks |
| 6 | The reschedule path emits an event the tick dispatches later, so the new reminder does not exist until the next tick | Accepted: up to five minutes, and a reminder is anchored hours or days out |
| 7 | The no-show sweep runs before the batch every tick | It is one indexed query against `(status, end_at)`; the index was added for exactly this |

## 12. References

- `docs/specs/SPEC-009-automation-substrate.md` §11 — the defects this closes.
- `docs/specs/SPEC-018-unified-tasks.md` — the inbox a failed automation lands in.
- `docs/05-operations/production-enablement-runbook.md` — how the engine is enabled.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version; implemented in phase 18 |
