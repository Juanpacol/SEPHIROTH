---
id: SPEC-018
title: Unified Clinical Tasks
phase: 16
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-009, SPEC-017]
adrs: []
features: [F-077, F-078, F-079, F-080, F-081]
diagrams: []
---

# SPEC-018 — Unified Clinical Tasks

## 1. Summary

One inbox for everything a clinician has to do. A `Task` is a persisted,
assignable, snoozable, closable handle on work whose authority lives elsewhere —
an alert, an approval, a follow-up, a result, a failed automation — plus the
work that has no row at all, like a worsening lab trend or an interacting drug
pair.

The existing entities keep their own state and their own routes. This is
additive: nothing is replaced, and one flag decides whether the dashboard reads
tasks or keeps re-deriving.

## 2. Motivation

Work is scattered across five inboxes and one read-only list:

- `/api/alerts` (`platform/api/routers/alerts.py`) — review and resolve.
- `/api/approvals` (`approvals.py`) — approve or reject a patient message.
- `/api/followups` (`followups.py`) — cancel a plan.
- `/api/results` (`results.py`) — share a result.
- `/api/scheduling` (`scheduling.py`) — confirm, complete, mark no-show.
- `GET /api/dashboard/action-items` (`dashboard.py:528`) — a flat, ranked,
  patient-named list derived at read time from all of the above **plus** four
  categories that have no row anywhere: a deteriorating trend, a drug
  interaction, an unreviewed imaging study, an unacted high-risk consultation.

That last endpoint is the concrete motivation. It already knows what a clinician
should do today, and it cannot help them do it: items have no id, no state, no
assignee, no due date, no history. Nothing on it can be claimed, snoozed,
commented on, or tracked to closure — a clinician reads it and then goes
somewhere else to act.

Two dead columns say the same thing from the other end: `Alert.assigned_to_user_id`
and `Alert.due_at` (`data/schemas/__init__.py:547,550`) were added in phase 9 and
are written by nothing.

## 3. Goals

- **G-1** Every piece of outstanding clinical work has one row, with an id.
- **G-2** That row can be assigned, taken, snoozed, commented on, closed and
  reopened, and every one of those is attributable to a person.
- **G-3** Acting on the source and acting on the task have the same effect, in
  both directions.
- **G-4** Re-deriving work on every tick does not accumulate duplicates, and
  work whose condition has passed does not linger.
- **G-5** The dashboard's existing response shape does not change.

## 4. Non-Goals

- **NG-1** The source entities are not replaced or deprecated. `Alert`,
  `PendingAction` and the rest keep their own lifecycle and routes.
- **NG-2** No multi-tier escalation ladder. `escalate` raises a counter; who
  gets told is still SPEC-009's single-tier fan-out.
- **NG-3** No task creation by hand. Every task comes from a source or a rule;
  a free-text to-do list is a different product.
- **NG-4** No cross-clinic assignment or team model. Assignment is to a user.
- **NG-5** The alert table's dead `assigned_to_user_id`/`due_at` columns are
  left in place, so this phase stays purely additive. Removing them is a later,
  separate change.

## 5. Definitions

- **Source** — the row a task refers to (`source_type` + `source_id`), or, for
  a derived task, the condition it stands for.
- **Derived task** — one with no source row: `deteriorating`, `interaction`,
  and the `result`/`consultation` sweeps. Owned end to end by
  `task_derivation`, which both creates and retires them.
- **Superseded** — the task's reason to exist is gone. Not a failure, not a
  dismissal, and terminal.

## 6. Contracts

### 6.1 Types

`data/schemas/__init__.py`: `Task` and `TaskEvent`. See §1 of each class
docstring for the design rationale; the fields that carry invariants:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `Task.dedupe_key` | String(160) | yes | — | unique; the identity of the *work*, not of the row |
| `Task.source_type` | String(30) | yes | — | one of the nine values in `ck_task_source_type` |
| `Task.source_id` | String(64) | no | null | null only for a condition with no row |
| `Task.status` | String(12) | yes | `open` | `ck_task_status`; a closed task needs `closed_by` |
| `Task.severity` | String(10) | yes | — | `ck_task_severity`; drives `due_at` via the SLA table |
| `Task.detail`, `Task.context` | Encrypted | yes | `""`/`{}` | free clinical text, so ADR-014 applies |
| `TaskEvent.actor_user_id` | FK users | no | null | null means the system did it |

### 6.2 Interfaces

```python
# platform/api/services/task_service.py  -- never commits
async def create_task(session, *, source_type, category, severity, title,
                      dedupe_key, ...) -> tuple[Task, bool]
async def transition(session, task, action, *, actor, now, **kwargs) -> Task
async def comment(session, task, *, actor, body) -> TaskEvent
async def close_tasks_for_source(session, source_type, source_id, *, status, actor, reason) -> int
async def reopen_due_snoozed(session, now) -> int
async def list_tasks(session, filters: TaskFilters) -> TaskPage

# platform/api/services/task_adapters.py
def can_complete(task) -> tuple[bool, str]
async def complete_task(session, task, *, actor, now) -> Task
async def reconcile_tasks(session, now, limit=200) -> int

# platform/api/services/task_derivation.py
async def sync_derived_tasks(session, now) -> dict[str, int]
```

`TRANSITIONS`, `EVENT_FOR_ACTION` and `SYSTEM_ONLY_ACTIONS` are exported so
tests assert against the tables themselves rather than re-deriving them.

### 6.3 State machine

| From | Action | To | Guard |
|---|---|---|---|
| open, snoozed | claim | in_progress | unassigned, or already the actor's; enforced in the UPDATE's WHERE clause |
| open, in_progress | assign | unchanged | target is an active user |
| open, in_progress | snooze | snoozed | future, ≤ 7 days, severity ≠ critical |
| snoozed | resume | in_progress | — |
| snoozed | (tick) | open | `snoozed_until <= now`; records no event |
| open, in_progress, snoozed | complete | done | the source adapter permits it; actor required |
| open, in_progress, snoozed | dismiss | dismissed | non-empty reason; actor required |
| open, in_progress, snoozed | escalate | unchanged | level < 2 |
| open, in_progress, snoozed | supersede | superseded | system only |
| done, dismissed | reopen | open | within 30 days |
| superseded | — | — | terminal |

### 6.4 Errors

`TaskTransitionError(ValueError)` for every refused transition and failed
guard. Deliberately not an `HTTPException`: the tick performs transitions too
and has no response to raise into. `platform/api/routers/tasks.py` maps it to
409 in one place.

### 6.5 Configuration

| Key | Type | Default | Rule |
|---|---|---|---|
| `enable_task_inbox` | bool | `False` | gates **only** the tick's derivation sweep and `/api/dashboard/action-items` reading from `tasks`. Task writes from source adapters are unconditional, so the table is warm before the flag flips |

## 7. Behaviour

- **B-1** `create_task` MUST be idempotent on `dedupe_key`, and MUST NOT revive
  a superseded task with that key.
- **B-2** A task's `due_at` MUST derive from severity via the SLA table, except
  where the source carries its own deadline.
- **B-3** `SLA_WINDOW_BY_SEVERITY` MUST be the only copy of that table;
  `alert_escalation` re-exports rather than duplicates it.
- **B-4** Claiming MUST be a single UPDATE whose WHERE clause carries the
  guard, so a claim issued from a stale read loses.
- **B-5** A transition absent from `TRANSITIONS` MUST raise, never fall through.
- **B-6** `supersede` MUST be refused to a clinician; `complete`/`dismiss` MUST
  be refused to the system.
- **B-7** A critical task MUST NOT be snoozable; a dismissal MUST carry a
  reason.
- **B-8** Every transition MUST record a `TaskEvent` naming its actor, and
  every recorded `event_type` MUST be one `ck_task_event_type` allows.
- **B-9** Resolving an `Alert` through its own route MUST close the alert's
  task in the same transaction, and completing an alert task MUST resolve the
  alert — both through the same implementation.
- **B-10** An approval task MUST refuse completion from the inbox, and the list
  response MUST say so before the button is offered.
- **B-11** `reconcile_tasks` MUST run every tick and supersede tasks whose
  source is gone or terminal.
- **B-12** `sync_derived_tasks` MUST retire a derived task whose condition no
  longer holds, and MUST NOT touch a task of a source type it does not own.
- **B-13** Listing tasks MUST write a `PhiAccessLog` row per patient exposed.
- **B-14** `/api/dashboard/action-items` MUST return the same items with the
  flag on and off, differing only by added optional fields.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-018-01 | Two tasks cannot share a `dedupe_key` | B-1 | `tests/test_task_service_transitions.py::TestDatabaseConstraints` |
| AC-018-02 | The database refuses a done/dismissed task with no `closed_by` | B-6 | `tests/test_task_service_transitions.py::TestDatabaseConstraints` |
| AC-018-03 | Every allowed transition lands on the state the table names | B-5 | `tests/test_task_service_transitions.py::TestAllowedTransitions` |
| AC-018-04 | Every (status, action) pair absent from the table raises | B-5 | `tests/test_task_service_transitions.py::test_every_pair_absent_from_the_table_is_refused` |
| AC-018-05 | Snooze cap, critical-cannot-snooze, dismissal reason, inactive assignee and system-only actions are all enforced | B-6, B-7 | `tests/test_task_service_transitions.py::TestRejectedTransitions` |
| AC-018-06 | Every transition records an event naming its actor, with an `event_type` the CHECK allows | B-8 | `tests/test_task_service_transitions.py::TestHistory` |
| AC-018-07 | The inbox lists worst-first and pages with offset while reporting the full total | G-1 | `tests/test_tasks_router.py::TestListing` |
| AC-018-08 | Listing writes one `PhiAccessLog` row per patient, and a patient account is refused | B-13 | `tests/test_tasks_router.py::TestListing` |
| AC-018-09 | A refused transition over HTTP is 409, not 500 | §6.4 | `tests/test_tasks_router.py::TestTransitionsOverHttp` |
| AC-018-10 | A claim issued from a stale read loses | B-4 | `tests/test_tasks_router.py::test_a_second_claim_is_refused_even_from_stale_state` |
| AC-018-11 | Both directions of alert/task consistency hold, and an approval task refuses completion | B-9, B-10 | `tests/test_tasks_router.py::TestSourceConsistency` |
| AC-018-12 | Three sweeps produce N tasks, not 3N | B-1 | `tests/test_task_derivation.py::TestIdempotency` |
| AC-018-13 | A resolved condition supersedes its task, and a later sweep does not revive it | B-12 | `tests/test_task_derivation.py::TestRetirement` |
| AC-018-14 | The sweep never supersedes a task of a source type it does not own | B-12 | `tests/test_task_derivation.py::test_the_sweep_never_touches_tasks_it_does_not_own` |
| AC-018-15 | `/action-items` returns the same items with the flag on and off | B-14 | `tests/test_action_items_compatibility.py::test_both_paths_return_the_same_items_for_the_same_fixture` |
| AC-018-16 | `/bootstrap` keeps its three top-level keys under both flag positions | B-14 | `tests/test_action_items_compatibility.py::test_bootstrap_keeps_its_three_top_level_keys` |
| AC-018-17 | Resolving removes the row before the server answers | G-2 | `platform/frontend/app/tasks/__tests__/page.test.tsx` |
| AC-018-18 | A refused action restores the row and says why | G-2 | `platform/frontend/app/tasks/__tests__/page.test.tsx` |

AC-018-17/18 are vitest suites; they are registered in
`tests/test_docs_gates.py::FRONTEND_ACCEPTANCE_CRITERIA`, which asserts the
named file exists and contains the id — see SPEC-017 §8 for why the docs gate
is satisfied that way rather than by widening its grep.

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Model | constraints, uniqueness, encrypted round-trip | `tests/test_task_service_transitions.py::TestDatabaseConstraints` |
| Service | the whole transition table, both directions | `tests/test_task_service_transitions.py` |
| Service | idempotency and retirement of derived work | `tests/test_task_derivation.py` |
| API | listing, filters, paging, PHI audit, role | `tests/test_tasks_router.py` |
| Compatibility | both sides of the flag | `tests/test_action_items_compatibility.py` |
| Frontend | optimistic remove and rollback | `platform/frontend/app/tasks/__tests__/page.test.tsx` |
| Migration | drift guard | `tests/test_alembic_migration.py` |

## 10. Migration & Compatibility

One Alembic revision, `98e0a1e35b4a`, purely additive: `tasks` and
`task_events`, nothing altered. Hand-corrected after autogenerate — it emitted
`core.crypto.EncryptedText()` with no import for it, the fixup
`docs/04-development/setup.md` warns about; the stored column is TEXT
ciphertext either way.

`scripts/backfill_tasks.py` files existing open alerts and pending approvals.
Deliberately a script rather than part of the migration: it needs the SLA table
and the adapter registry, which are application code a migration must not
import. Safe to re-run. Derived work is **not** backfilled — the tick
re-derives all of it within five minutes, and doing it twice would risk two
versions of the same rule disagreeing.

Nothing is shimmed. The dashboard's old derivation stays in place behind the
flag and is the rollback path.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | `source_type` + `source_id` gives no referential integrity to the source | Accepted, and forced: the sources have incompatible primary-key types (`LabResult.id` and `TimelineEvent.id` are integers), and two categories have no source row at all. Bounded by `ck_task_source_type` and by `reconcile_tasks` |
| 2 | A source closed by a bulk UPDATE leaves its task open until the next tick | Accepted and documented: up to one tick — five minutes — a task can name work that no longer exists. `approvals.py::_expire_due_pending` is exactly this case, and `reconcile_tasks` exists for it |
| 3 | Persisting derived work means it can linger after its condition passes | This is why `task_derivation` owns both halves. A persisted inbox with only the create half is worse than the derived list it replaced, because it accumulates |
| 4 | The real concurrent-claim race cannot be tested here | Every request shares one `AsyncSession` through the dependency override, and an AsyncSession used from two tasks at once raises rather than racing. The test asserts the property that makes the race safe instead — a claim from a stale read loses — which is what the WHERE-clause guard buys |
| 5 | Two categories still have no adapter behaviour (`appointment`, `automation`) | They are registered with no terminal statuses, so `reconcile_tasks` leaves them alone. Their producers land in SPEC-020 |
| 6 | `_resolve_alert` is imported into the router by its private name | Accepted for now: it is one call site and the alternative is a public wrapper that does nothing. Revisit if a third caller appears |

## 12. References

- `docs/specs/SPEC-009-automation-substrate.md` — the tick this hooks into.
- `docs/specs/SPEC-017-interface-foundations.md` — the primitives the inbox is
  built from, and the frontend-AC convention.
- `docs/08-decisions/ADR-014-phi-column-encryption.md` — why `detail`/`context`
  are encrypted columns.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version; implemented in phase 16 |
