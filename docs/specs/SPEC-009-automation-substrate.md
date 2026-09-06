---
id: SPEC-009
title: Automation Substrate
phase: 7
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-000]
adrs: []
features: [F-060, F-061, F-062, F-063, F-064, F-065, F-066, F-067, F-068, F-069, F-070, F-071]
diagrams: []
---

# SPEC-009 — Automation Substrate

## 1. Summary

The durable workflow substrate that turns clinical events into scheduled,
retryable, auditable work: a tick engine (claim/lease/retry), a transactional
event outbox, and the seven workflow definitions built on them — alert
escalation, appointment reminders and unconfirmed-appointment escalation,
human-in-the-loop approvals, patient follow-up, operational memory, and
automation observability.

**This spec is retroactive.** The behaviour it describes was implemented across
phases 7–14 and has been live and tested since; the spec was never written.
`docs/project-state.yaml` referenced SPEC-009 through SPEC-016 as if they
existed. This document consolidates all eight into one, because they share a
single substrate and splitting them after the fact would produce seven specs
that each describe a handler. Recording it now serves two purposes: later specs
have something to declare `depends_on` against, and §11 records the defects the
substrate is known to carry, which is what the next phase is scoped to fix.

Numbers SPEC-010 through SPEC-016 are permanently retired — never reused, per
SPEC-000 §6.3 ("specs are never renumbered").

## 2. Motivation

Before phase 7, everything the application did happened inside a request. A
reminder that must fire 24 hours before an appointment, an alert that must
escalate if nobody reviews it within its severity window, a follow-up due on day
30 — none of those have a request to hang off. `platform/api/routers/scheduling.py`
could create an appointment but had nowhere to put "and remind them tomorrow".

The constraint that shaped every decision here: the deployment is a single
free-tier instance (`render.yaml`) with **no worker process, no Redis, no
Celery, and no in-process scheduler**. Time has to enter the system from
outside, which is why the substrate is a tick endpoint driven by an external
cron rather than a queue.

## 3. Goals

- **G-1** A unit of future work survives process restart and is executed exactly
  once, even if two ticks overlap.
- **G-2** A failing step retries on a bounded backoff and then stops, without a
  human noticing it never finished.
- **G-3** A domain event recorded during a request reaches its subscribers
  without a broker, and without the emitting request depending on delivery.
- **G-4** Nothing the substrate does to a patient's record happens without an
  audit row, including when the handler that read it then failed.
- **G-5** No message reaches a patient without a clinician approving it.
- **G-6** An operator can tell, without database access, whether the engine is
  running and what it failed at.

## 4. Non-Goals

- **NG-1** No worker process, message broker, or in-process scheduler. Time
  enters via `POST /internal/tick` only.
- **NG-2** No sub-tick latency. Cron granularity is 5 minutes; every guarantee
  here is "eventually, within a tick or two", never "immediately".
- **NG-3** No LLM call inside a tick. Handlers are deterministic; drafting is
  requested later, from a request path (`platform/api/routers/approvals.py`).
- **NG-4** No delivery channel other than in-app. `channels.py` is the seam
  where another one would go; `contact_preference` validates `'in_app'` and
  nothing else.
- **NG-5** No rule engine expressed as data. Step types are a literal dict of
  Python handlers, the same call `src/sephiroth/tools/servers.py::TOOL_CAPABILITIES`
  makes.

## 5. Definitions

- **Tick** — one invocation of `run_tick`, bounded by
  `workflow_tick_budget_seconds` and `workflow_tick_batch_size`.
- **Step** — one unit of scheduled work (`WorkflowStep`), owned by a `Workflow`,
  typed by a `step_type` registered in `STEP_TYPES`.
- **Lease** — the interval during which a claimed step belongs to one tick.
  Past `lease_expires_at`, another tick may reclaim it.
- **Stale** — due so long ago that running it now would be wrong rather than
  late (`max_lateness_seconds`). A stale step is skipped, not failed.
- **Superseded** — the step's reason to exist disappeared (the appointment was
  cancelled, the alert was already reviewed). Not a failure.

## 6. Contracts

### 6.1 Types

`platform/api/workflows/registry.py`:

```python
@dataclass(frozen=True)
class StepContext:
    session: AsyncSession
    step: WorkflowStep
    workflow: Workflow
    now: datetime
    channel: NotificationChannel


@dataclass(frozen=True)
class StepResult:
    outcome: Literal["succeeded", "skipped", "superseded"]
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepTypeSpec:
    step_type: str
    handler: StepHandler
    max_attempts: int = 3
    max_lateness_seconds: int | None = None
    timeout_seconds: float = 5.0
    reads_phi: bool = True
```

Persisted shapes are in `data/schemas/__init__.py`: `Workflow`, `WorkflowStep`,
`WorkflowEvent`, `PendingAction`, `FollowupPlan`, `AutomationMemory`.

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `WorkflowStep.status` | str | yes | `pending` | one of pending, running, succeeded, failed, skipped, superseded, cancelled |
| `WorkflowStep.attempts` | int | yes | 0 | incremented by the claim CAS, never by the handler |
| `WorkflowStep.lease_expires_at` | datetime | no | null | naive UTC; set on claim, meaningful only while `running` |
| `WorkflowEvent.status` | str | yes | `pending` | one of pending, dispatched, no_subscriber |
| `PendingAction.status` | str | yes | `pending` | one of pending, approved, rejected, expired |
| `AutomationMemory.key` | str | yes | — | must appear in `_KEY_SPECS`; its value must satisfy that key's validator |

Every datetime in this subsystem is **naive UTC**. `func.now()` is never used in
a predicate: Postgres returns it timezone-aware and the comparison would fail
against the naive columns.

### 6.2 Interfaces

```python
# platform/api/workflows/engine.py
async def reclaim_expired_leases(session, now) -> int
async def select_due_step_ids(session, now, batch_size) -> list[str]
async def claim_step(session, step_id, tick_id, now, lease_seconds) -> bool
async def execute_step(session, step_id, now) -> str   # succeeded|failed|skipped|error
async def run_tick(session, tick_id) -> TickSummary

# src/sephiroth/workflows/events.py
def emit(session, event_type, *, entity_type, entity_id, patient_id, payload) -> WorkflowEvent
async def dispatch_pending(session) -> int

# src/sephiroth/workflows/policy.py  (pure)
def is_stale(due_at, now, max_lateness_seconds) -> bool
def next_run_after(attempts, now) -> datetime
def classify_step_failure(exc) -> Failure
def decide_step_recovery(attempts, max_attempts) -> RecoveryActionType

# platform/api/workflows/channels.py
class NotificationChannel(Protocol):
    async def send(self, session, user_id, type_, message, *,
                   dedupe_key=None, related_appointment_id=None) -> bool
```

`emit` stages a row in **the caller's transaction** and does not commit: an
event exists if and only if the change that caused it was committed.
`send` returns `False` when `dedupe_key` was already used — a duplicate is a
no-op, never an error.

### 6.3 State machine

Step lifecycle. The table is normative.

| From | Event | To | Guard |
|---|---|---|---|
| pending | claim | running | `status == 'pending'` at CAS time (exactly one winner) |
| running | lease expired | pending | `lease_expires_at < now` |
| running | handler returns `succeeded` | succeeded | — |
| running | handler returns `skipped`/`superseded` | skipped/superseded | — |
| running | due past lateness window | skipped | `is_stale(due_at, now, max_lateness)` |
| running | handler raised, attempts remain | pending | `decide_step_recovery == RETRY`; `run_after = next_run_after(attempts, now)` |
| running | handler raised, attempts exhausted | failed | `decide_step_recovery == ABSTAIN` |
| running | unknown `step_type` or missing parent workflow | failed | terminal immediately, no retry |
| pending | parent cancelled | cancelled | via `instantiate.py::cancel_workflow` |

A `Workflow` auto-completes when no step of it remains `pending` or `running`
(`engine.py:187`).

Approval lifecycle: `pending → approved | rejected | expired`, terminal in all
three; a second transition is rejected (`test_approvals_api.py::test_cannot_approve_twice`).

### 6.4 Errors

Handler exceptions never propagate past `execute_step`. They are classified by
`classify_step_failure` into `sephiroth.contracts.enums.FailureCategory` and
recorded on `WorkflowStep.failure_category`/`last_error`. `asyncio.TimeoutError`
from the per-step `asyncio.wait_for` is classified the same way as any other
exception. `InvalidMemoryKey` (`workflows/memory.py`) is a `ValueError` raised
on an unknown scope or key, or a value that fails that key's validator.

### 6.5 Configuration

| Key | Type | Default | Rule |
|---|---|---|---|
| `enable_workflow_engine` | bool | `False` | when `False`, `POST /internal/tick` returns `{"status":"disabled"}` and does no work |
| `internal_tick_token` | str | `""` | ≥32 chars required at boot when the engine is enabled in production (`Settings._check_tick_token`) |
| `workflow_tick_batch_size` | int | 25 | maximum steps claimed per tick |
| `workflow_tick_budget_seconds` | float | — | wall-clock budget; the loop breaks when exceeded |
| `workflow_step_lease_seconds` | int | — | lease length granted at claim |
| `workflow_step_timeout_seconds` | float | — | **dead**: the engine uses `StepTypeSpec.timeout_seconds` instead |
| `slack_webhook_url` | str | `""` | setting it is what enables operator tick notifications |
| `clinical_slack_webhook_url` | str | `""` | separate channel for the clinical digest |

## 7. Behaviour

- **B-1** A step MUST be claimed by a status compare-and-swap, so two concurrent
  ticks selecting the same step produce exactly one winner.
- **B-2** The claim CAS MUST be the only place `attempts` is incremented.
- **B-3** A step left `running` past its lease MUST be returned to `pending` at
  the top of the next tick.
- **B-4** A step whose due time is past its lateness window MUST be skipped
  without invoking its handler.
- **B-5** When a step type declares `reads_phi`, its `PhiAccessLog` row MUST be
  committed **before** the handler runs, so it survives the rollback of a failed
  attempt.
- **B-6** A handler exception MUST NOT propagate out of `execute_step`; the step
  retries on the policy backoff while attempts remain, then terminates as
  `failed`.
- **B-7** `emit` MUST stage its row in the caller's transaction and MUST NOT
  commit; a rolled-back caller leaves no event.
- **B-8** `dispatch_pending` MUST mark an event `no_subscriber` rather than
  failing when no handler is registered for its type, and MUST NOT process an
  already-dispatched event twice.
- **B-9** A duplicate `dedupe_key` MUST make `NotificationChannel.send` a no-op
  returning `False`, never an integrity error surfaced to the caller.
- **B-10** An alert MUST NOT be resolvable before it has been reviewed.
- **B-11** Resolving an alert MUST cancel its still-active escalation workflow.
- **B-12** An escalation's due time MUST derive from the alert's severity.
- **B-13** A new appointment MUST enrol exactly one reminder step and one
  unconfirmed-check step, and re-enrolment for the same appointment MUST be a
  no-op.
- **B-14** A step whose reason to exist has disappeared MUST return `superseded`,
  not `failed`.
- **B-15** A patient MUST only be able to confirm their own appointment.
- **B-16** A `PendingAction` MUST NOT reach `approved` without a reviewer
  recorded, enforced at the database level and not only in the router.
- **B-17** Approving MUST deliver the final text to the patient; rejecting MUST
  deliver nothing.
- **B-18** A follow-up plan MUST enrol steps at day 3, 7 and 30.
- **B-19** `set_memory` MUST reject an unknown scope, an unknown key, a value
  that fails its key's validator, and a `scope_id` naming no real user/patient;
  and MUST upsert rather than duplicate.
- **B-20** `POST /internal/tick` MUST authenticate by shared-secret header
  compared in constant time, and MUST require no authentication while the engine
  is disabled (it does nothing in that state).

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-009-01 | Two concurrent claims of one step yield exactly one winner | B-1, B-2 | `tests/test_workflow_engine_tick.py::test_claim_step_cas_race_only_one_winner` |
| AC-009-02 | A `running` step past its lease returns to `pending` | B-3 | `tests/test_workflow_engine_tick.py::test_reclaim_expired_leases_returns_step_to_pending` |
| AC-009-03 | A step past its lateness window is skipped, handler not invoked | B-4 | `tests/test_workflow_engine_tick.py::test_execute_step_past_max_lateness_is_skipped` |
| AC-009-04 | A raising handler retries while attempts remain, then fails terminally | B-6 | `tests/test_workflow_engine_tick.py::test_execute_step_retries_then_terminally_fails` |
| AC-009-05 | The `PhiAccessLog` row survives a handler failure and its rollback | B-5 | `tests/test_workflow_engine_tick.py::test_phi_audit_row_survives_handler_failure_and_rollback` |
| AC-009-06 | A workflow completes when its last step leaves the pending/running set | §6.3 | `tests/test_workflow_engine_tick.py::test_execute_step_success_completes_workflow_when_no_steps_remain` |
| AC-009-07 | A tick claims at most `batch_size` steps and reports what remains due | §6.5 | `tests/test_workflow_engine_tick.py::test_run_tick_respects_batch_size_and_reports_remaining` |
| AC-009-08 | Retry backoff grows with attempts and is capped | B-6 | `tests/test_workflow_policy.py::test_next_run_after_backoff_grows_and_caps` |
| AC-009-09 | Running `alert_refresh` twice creates no duplicate `Alert` | G-1 | `tests/test_workflow_alert_refresh.py::test_alert_refresh_handler_runs_twice_without_duplicating_alerts` |
| AC-009-10 | The tick endpoint rejects a missing or wrong token and accepts the right one | B-20 | `tests/test_internal_tick_auth.py::test_enabled_engine_rejects_wrong_token` |
| AC-009-11 | A rolled-back caller leaves no `WorkflowEvent` row | B-7 | `tests/test_workflow_events.py::test_emit_stages_row_that_rollback_discards` |
| AC-009-12 | Dispatch marks an unwired event `no_subscriber` and never processes one twice | B-8 | `tests/test_workflow_events.py::test_dispatch_pending_is_idempotent_no_double_processing` |
| AC-009-13 | A repeated `dedupe_key` makes `send` a no-op returning `False` | B-9 | `tests/test_workflow_channels.py::test_send_is_idempotent_on_dedupe_key` |
| AC-009-14 | Resolving an unreviewed alert is rejected | B-10 | `tests/test_alert_lifecycle_api.py::test_resolve_without_review_is_rejected` |
| AC-009-15 | Resolving an alert cancels its active escalation workflow | B-11 | `tests/test_alert_lifecycle_api.py::test_resolve_cancels_active_escalation_workflow` |
| AC-009-16 | Escalation due time derives from alert severity | B-12 | `tests/test_alert_escalation_workflow.py::test_on_clinical_alert_creates_workflow_with_correct_due_date` |
| AC-009-17 | A new appointment enrols two steps at the correct offsets, idempotently | B-13 | `tests/test_appointment_reminder_workflow.py::test_on_new_appointment_enrolls_two_steps_at_correct_offsets` |
| AC-009-18 | A cancelled appointment's reminder returns `superseded` | B-14 | `tests/test_appointment_reminder_workflow.py::test_send_reminder_t24_superseded_after_cancellation` |
| AC-009-19 | A patient cannot confirm another patient's appointment | B-15 | `tests/test_api_appointment_confirm.py::test_patient_cannot_confirm_another_patients_appointment` |
| AC-009-20 | The database refuses an approved action with no reviewer | B-16 | `tests/test_approvals_api.py::test_db_level_constraint_blocks_approved_without_reviewer` |
| AC-009-21 | Approving delivers the final text; rejecting delivers nothing | B-17 | `tests/test_approval_send_path.py::test_reject_sends_nothing` |
| AC-009-22 | A follow-up plan enrols three steps at day 3, 7 and 30 | B-18 | `tests/test_patient_followup_workflow.py::test_enroll_plan_creates_three_steps_at_correct_offsets` |
| AC-009-23 | A cancelled plan supersedes its due follow-up step | B-14 | `tests/test_patient_followup_workflow.py::test_followup_check_due_superseded_when_plan_cancelled` |
| AC-009-24 | `set_memory` rejects unknown key, unknown scope, and malformed value | B-19 | `tests/test_automation_memory.py::test_set_rejects_malformed_value_for_known_key` |
| AC-009-25 | `set_memory` upserts rather than duplicating | B-19 | `tests/test_automation_memory.py::test_set_upserts_not_duplicates` |
| AC-009-26 | The automation dashboard counts overdue steps | G-6 | `tests/test_dashboard_automation.py::test_automation_dashboard_counts_overdue_steps` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | staleness, backoff, failure classification, recovery decision | `tests/test_workflow_policy.py` |
| Engine | claim CAS, lease reclaim, retry/terminal, PHI audit durability, batch budget | `tests/test_workflow_engine_tick.py` |
| Outbox | transactional emit, dispatch, idempotency | `tests/test_workflow_events.py` |
| Channel | in-app delivery, dedupe | `tests/test_workflow_channels.py` |
| Definitions | one module per workflow definition | `tests/test_workflow_alert_refresh.py`, `test_alert_escalation_workflow.py`, `test_appointment_reminder_workflow.py`, `test_patient_followup_workflow.py` |
| End to end | subscriber → step → notification | `tests/test_alert_escalation_end_to_end.py`, `test_appointment_reminder_end_to_end.py` |
| API | alert lifecycle, approvals, follow-ups, confirm, memory, automation dashboard | `tests/test_alert_lifecycle_api.py`, `test_approvals_api.py`, `test_approval_send_path.py`, `test_api_followups.py`, `test_api_appointment_confirm.py`, `test_api_automation_memory.py`, `test_dashboard_automation.py` |
| Auth | tick shared secret | `tests/test_internal_tick_auth.py` |
| Ops | Slack payload allow-list (never PHI) | `tests/test_ops_notify.py`, `tests/test_clinical_notify.py` |

## 10. Migration & Compatibility

Shadows nothing and shims nothing: the substrate is additive, and the whole of
it is gated by `enable_workflow_engine`. With the flag off, no code path in the
application changes — which is what makes the rollback in
`docs/05-operations/production-enablement-runbook.md` a flag flip rather than a
deploy.

The split between `src/sephiroth/workflows/` and `platform/api/workflows/`
follows ADR-010 (runtime separate from application): pure policy and the event
outbox live in `src/`, everything holding SQL for steps lives in `platform/`.
`events.py` is the deliberate exception — it touches the database from `src/` so
that `src/sephiroth/safety/alerts.py`, which is already clinical logic living in
`src/`, can call `emit()` without `platform/` importing back into `src/` against
the intended direction.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | `execute_step` passes `spec.max_lateness_seconds`, ignoring the per-row `WorkflowStep.max_lateness_seconds` that `on_new_appointment` and `enroll_plan` populate (`engine.py:128`). The column is dead. | Known defect. Fixed in SPEC-020. |
| 2 | `alert_refresh` runs once: it returns `succeeded`, no steps remain, the parent workflow completes, and nothing reschedules it. "Periodic" is aspirational. | Known defect. Fixed in SPEC-020, which adds a `deferred` outcome. |
| 3 | Rescheduling an appointment silently loses its reminder: `update_appointment` neither cancels nor re-enrols, and the idempotency guard would block re-enrolment even if an event were emitted. | Known defect. Fixed in SPEC-020. |
| 4 | `quiet_hours` and `reminder_lead_hours` are validated and stored but read by nothing (`workflows/memory.py:11-17` says so in its own docstring); the reminder lead time is the hard-coded `REMINDER_LEAD_TIME`. | Deliberate deferral: honouring them needs a "not now, try later" step outcome the engine lacks. Added in SPEC-020. |
| 5 | `MISSED_APPOINTMENT` and `FOLLOWUP_DUE` are declared event types with no producer, and `PATIENT_MESSAGE` has no subscriber. | `MISSED_APPOINTMENT` gets a producer in SPEC-020. The other two remain unwired. |
| 6 | `followup_check_due` creates a `PendingAction` with an empty draft; the approvals inbox can show a row with nothing in it until someone requests a draft. | Fixed in SPEC-020 with a deterministic template plus a database-level non-empty constraint. |
| 7 | Retry backoff has no jitter, so steps that fail together retry together. | Accepted at this scale: the 5-minute cron granularity dwarfs a 30-second base, and `batch_size` caps concurrency. Revisited in SPEC-020 for the periodic case only. |
| 8 | `/internal/tick` is protected by a shared secret with no rate limit. | Accepted and documented in the runbook; the mitigation is token rotation. |
| 9 | The free-tier instance spins down when idle, so the first tick after a quiet period pays a cold start longer than cron-job.org's timeout, reporting a failure for a tick that in fact ran. | Accepted; an argument for the on-premise deployment target in SPEC-022. |

## 12. References

- `docs/00-migration-charter.md` — frozen contracts and phase rules.
- `docs/05-operations/production-enablement-runbook.md` — how the engine is
  turned on in production, and how it is rolled back.
- `docs/08-decisions/ADR-010-runtime-separate-from-application.md` — why the
  substrate is split across `src/` and `platform/`.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Retroactive consolidation of the phase 7–14 automation substrate, written after the fact; records the defects it ships with in §11 |
