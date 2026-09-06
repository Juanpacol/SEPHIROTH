---
id: SPEC-027
title: Hardening — The Datetime Contract, The Permission Matrix, and Bounded Reads
phase: 25
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-018, SPEC-024]
adrs: []
features: [F-110, F-111, F-112]
diagrams: []
---

# SPEC-027 — Hardening

## 1. Summary

An audit, and the three things it found worth fixing: one endpoint that stores
a correctly-sent time at the wrong hour, a permission boundary that was solid
but unproven, and list endpoints that return every row a clinic has ever
produced.

Everything here was measured before it was written. Two things this phase was
scoped to fix turned out already to be right, and are recorded as such rather
than churned.

## 2. Motivation

### The finding that matters: a blocked hour is stored at the wrong hour

`POST /api/scheduling/exceptions` — how a clinician blocks time for surgery, a
holiday, an afternoon off — does no timezone handling at all. Its five sibling
endpoints in the same router each guard the input:

```python
if body.start_at.tzinfo is None:
    raise HTTPException(status_code=422, detail="start_at must be timezone-aware")
start_at = body.start_at.astimezone(timezone.utc).replace(tzinfo=None)
```

`create_exception` has neither line. Measured, not inferred:

| Sent | Stored | Should be |
|---|---|---|
| `2026-09-07T09:00:00-05:00` | `09:00` | `14:00` |

A clinician in Bogotá blocking 09:00–12:00 for surgery blocks 09:00–12:00 **UTC**
— 04:00–07:00 their time. The block lands on hours nobody works, and
`expand_slots` offers the surgery hours as available. Patients get booked into
the operating theatre.

It is invisible on a UTC server, which is what the public demo runs on. It is
five hours wrong on the on-premise deployment SPEC-022 made the default target.

Second defect, same handler: comparing an aware `start_at` against a naive
`end_at` raises `TypeError: can't compare offset-naive and offset-aware
datetimes` — an unhandled 500 where a 422 belongs.

### The boundary was solid, and nothing said so

Probing all 143 routes with no credentials: 135 refuse, 8 do not, and all 8 are
correct — two health checks and six authentication entry points. That is a good
result and it was nobody's to rely on, because no test asserted it. The next
router mounted without a guard would be found by a person, or not at all.

### Reads that grow forever

`GET /api/alerts` and `GET /api/scheduling/appointments` build a query, apply
filters, and return every matching row. On a clinic with three years of history
that is every alert ever raised and every appointment ever booked, serialised
into one response.

### What the audit found already correct

Recorded so the next audit does not redo it:

- **The five other scheduling datetime endpoints** guard naive input properly.
- **Indexes** cover the hot paths on `alerts`, `appointments`, `tasks`,
  `result_reviews`, `workflow_steps` and `phi_access_log`. Two gaps, both
  small, are closed in §6.
- **Concurrency**: `claim_step` and `task_service.transition` use
  compare-and-set with a row count. The read-modify-write in task claiming was
  found and fixed in phase 19.

## 3. Goals

- **G-1** One datetime contract across the API, enforced rather than repeated.
- **G-2** The permission boundary is a measured fact, and stays one.
- **G-3** No endpoint returns an unbounded number of rows.
- **G-4** Findings that turned out to be non-issues are written down.

## 4. Non-Goals

- **NG-1** No response-shape changes. Endpoints returning a bare list keep
  returning one; a cap plus `X-Total-Count` says what was left out without
  breaking a caller.
- **NG-2** No rate-limit changes. `core/rate_limit.py` exists and works.
- **NG-3** No auth mechanism changes. The boundary is proven, not redesigned.
- **NG-4** No query rewriting for speed. Two indexes are added because they are
  missing; nothing is optimised on a table nobody has profiled.
- **NG-5** No timezone *storage* change. Every column stays naive UTC — that is
  the convention, it is consistent, and changing it is a migration across
  thirty tables to fix nothing.

## 5. Definitions

- **The datetime contract** — a request field of type `datetime` MUST carry an
  offset. Naive input is refused, never guessed at.
- **Bounded read** — an endpoint whose response size does not grow with the
  clinic's history.

## 6. Contracts

### 6.1 Types

No schema change beyond two indexes:

| Index | Table | Why |
|---|---|---|
| `ix_consultations_user_created` | `consultations (user_id, created_at)` | `GET /api/agents/history` filters by user and orders by recency; `created_at` had no index at all |
| `ix_timeline_events_patient_date` | `timeline_events (patient_id, date)` | every timeline read filters by patient and orders by date |

### 6.2 Interfaces

`platform/api/timeparse.py`:

```python
def require_aware(value: datetime, field: str) -> datetime:
    """An aware datetime as naive UTC, or 422. Never assumes."""
```

One function, called at every site that accepts a `datetime`. The five
scheduling endpoints that had the logic inline now call it; `create_exception`,
which had nothing, calls it too.

Capped endpoints gain `limit` and `offset` query parameters and an
`X-Total-Count` response header. The body shape does not change (NG-1).

| Endpoint | Default cap |
|---|---|
| `GET /api/alerts` | 200 |
| `GET /api/scheduling/appointments` | 500 |
| `GET /api/followups` | 200 |
| `GET /api/results/shares` | 200 |
| `GET /api/results/shareable/{patient_id}` | 200 |

### 6.3 State machine

`N/A`.

### 6.4 Errors

Naive datetime input → `422`, naming the field. Previously: silently wrong
(exceptions) or `500` (mixed aware/naive).

### 6.5 Configuration

`N/A`.

## 7. Behaviour

- **B-1** Every `datetime` field in a request body MUST refuse naive input with
  a `422` naming the field.
- **B-2** An aware datetime MUST be stored converted to UTC, never truncated.
- **B-3** Mixing aware and naive in one request MUST be a `422`, never a `500`.
- **B-4** Every route except the health checks and the authentication entry
  points MUST refuse an unauthenticated request.
- **B-5** A patient token MUST be refused by every clinician-only route.
- **B-6** A capped endpoint MUST return at most its cap and report the true
  total in `X-Total-Count`.
- **B-7** Storage MUST remain naive UTC everywhere.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-027-01 | A block sent with an offset is stored converted, and naive input is refused | B-1, B-2 | `tests/test_datetime_contract.py::TestSchedulingExceptions` |
| AC-027-02 | Mixed aware/naive is a 422, not a crash | B-3 | `tests/test_datetime_contract.py::TestSchedulingExceptions` |
| AC-027-03 | Every request model's datetime fields are covered by the contract | B-1 | `tests/test_datetime_contract.py::TestTheContractIsUniform` |
| AC-027-04 | Every route refuses an anonymous request, except a named list | B-4 | `tests/test_permission_matrix.py::TestNothingIsOpenByAccident` |
| AC-027-05 | A patient token is refused by every clinician route | B-5 | `tests/test_permission_matrix.py::TestRoleSeparation` |
| AC-027-06 | A capped endpoint caps, and says what it left out | B-6 | `tests/test_bounded_reads.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| HTTP | the datetime contract, per field and per endpoint | `tests/test_datetime_contract.py` |
| HTTP | all 143 routes × three credentials | `tests/test_permission_matrix.py` |
| HTTP | caps and totals | `tests/test_bounded_reads.py` |

## 10. Migration & Compatibility

One revision, two indexes, no data change.

**The exception fix changes behaviour for existing rows' successors, not for
existing rows.** Blocks already stored at the wrong hour stay where they are:
this phase cannot know whether a given historical row was sent aware (wrong) or
naive (right), and guessing would corrupt the ones that are correct. §11 risk 1
records how an operator finds them.

Callers sending naive datetimes to `POST /api/scheduling/exceptions` now get a
`422` where they previously got a `201`. That is the point — they were storing
an unintended time — and it matches what the other five endpoints have always
done.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Existing exception rows may hold the wrong hour | Not rewritten: the correct value depends on what the client sent, which is not recoverable from the row. The runbook gains a query listing exceptions whose hours look implausible for a working day, for a human to check. Fabricating a correction would corrupt the rows that are already right |
| 2 | A cap changes what a client sees | `X-Total-Count` says so on every response, and the caps are set well above a working clinic's page. The alternative is an endpoint that degrades until it times out |
| 3 | The permission matrix hardcodes the public routes | Deliberately: adding a route to that list is the moment somebody decides it is public, which is exactly where the decision should be visible |
| 4 | `require_aware` is not enforced by the type system | A test walks every request model and fails on a `datetime` field no endpoint guards. It is a structural check, like the PHI-seam one (ADR-015), for the same reason |

## 12. References

- `docs/specs/SPEC-018-unified-tasks.md` — the pagination shape new endpoints use.
- `docs/08-decisions/ADR-015-phi-egress-enumerated-seams.md` — the precedent for
  an enforced list rather than a convention.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
