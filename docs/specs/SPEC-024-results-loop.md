---
id: SPEC-024
title: Results With a Closed Loop
phase: 22
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-018, SPEC-021, SPEC-023]
adrs: [ADR-017]
features: [F-100, F-101, F-102, F-103]
diagrams: []
---

# SPEC-024 — Results With a Closed Loop

## 1. Summary

A result arrives, someone reads it, someone decides, the patient is told, and
the loop closes. Today only the middle two happen, informally, and nothing in
the system can say which results were never read.

This phase adds the way a result gets *in*, the record of what was decided
about it, and the guard that stops a result being marked done while the patient
who needs to hear about it has not been told.

## 2. Motivation

**Nothing creates a `LabResult`.** The table has existed for phases; four
modules read it and no code path anywhere writes one. Every trend, every
deterioration query, every "recent results" panel is reading a table that only
ever fills from a fixture. The most basic thing a clinic does with a lab — write
it down — has no home.

`Patient.lab_results` is the JSON panel the risk engine actually reads, and it
is a current-values snapshot with no history and no row identity. So the
product has two representations of a lab result, one that can be reasoned about
and is empty, and one that is full and cannot.

**And a result has no lifecycle.** `is_abnormal` and `is_critical` describe the
*value*; they say nothing about whether a human looked at it. A clinician can
open a chart, read a potassium of 6.2, decide it is expected on that patient's
regimen, and close the tab — and the system is in exactly the same state as if
nobody had ever opened it. The question a clinic gets sued over is "who saw this
and when", and there is nothing to answer it with.

**Only *critical* results become work.** `task_derivation._critical_labs`
filters on `is_critical`, so an abnormal-but-not-critical result — the
creatinine that drifted up, the HbA1c at 8.4 — produces nothing at all. Those
are the results that get missed, precisely because they do not shout.

**Sharing is attached to the wrong thing.** `ResultShare` references a
`TimelineEvent`, chosen when there was no result row worth referencing. That
made sense then and does not now: it means a result has two identities, and
"was this result communicated" cannot be asked of the result.

## 3. Goals

- **G-1** A result can be recorded, and its classification is a rule anyone can
  read.
- **G-2** Every result carries a state, so "which results has nobody read" is a
  query.
- **G-3** An abnormal result becomes work, not only a critical one.
- **G-4** A result cannot be closed while the patient it concerns has not been
  told, when telling them was the decision.
- **G-5** The clinician's decision is recorded in their own words, not inferred.

## 4. Non-Goals

- **NG-1** No HL7/FHIR ingestion. The intake endpoint takes JSON this product
  defines. A real interface engine is a project, and pretending an endpoint is
  one would invite pointing a lab feed at it.
- **NG-2** No reference-range management UI. Ranges are code, same reasoning as
  SPEC-021 §6.5 — a clinical cutoff that changes without review is a cutoff
  nobody reviews.
- **NG-3** No result *interpretation* by a model. The classification is
  arithmetic against a range. The model's only job here is turning a clinician's
  decision into plain language for the patient, through the existing approval
  gate.
- **NG-4** No backfill of `Patient.lab_results` into `LabResult`. The JSON panel
  has no timestamps, so inventing them would fabricate a history. New results
  write both (§6.5); old ones stay where they are.
- **NG-5** No migration of existing `ResultShare` rows onto results. They point
  at timeline events and keep doing so; the new link is additive
  (§10).
- **NG-6** No auto-close. Every terminal transition is a person's act.

## 5. Definitions

- **Result** — one `LabResult` or one `ImagingStudy`. Referenced by
  `(result_type, result_id)`, the same shape `tasks` uses, for the same reason:
  the two tables have incompatible primary-key types.
- **Disposition** — what the clinician decided: `normal`, `abnormal_expected`,
  `action_taken`, or `needs_patient_contact`.
- **Closed loop** — reviewed, disposed of, and — when the disposition was
  `needs_patient_contact` — communicated.

## 6. Contracts

### 6.1 Types

**`result_reviews`**

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `id` | String(36) | yes | — | PK |
| `result_type` | String(10) | yes | — | `ck_result_review_type`: lab/imaging |
| `result_id` | String(64) | yes | — | with `result_type`, unique |
| `patient_id` | FK patients | yes | — | |
| `status` | String(14) | yes | `received` | `ck_result_review_status` |
| `severity` | String(10) | yes | — | `normal`/`abnormal`/`critical`, from §6.5 |
| `reviewed_at` / `reviewed_by` | DateTime / FK users | no | null | `ck_result_review_reviewed` |
| `disposition` | String(24) | no | null | `ck_result_review_disposition` |
| `note` | EncryptedText | yes | `""` | the clinician's own words |
| `share_id` | FK result_shares | no | null | set when the patient is told |
| `closed_at` / `closed_by` | DateTime / FK users | no | null | `ck_result_review_closed` |
| `created_at` / `updated_at` | DateTime | yes | now | |

Unique on `(result_type, result_id)` — one lifecycle per result, so a second
intake of the same row cannot produce a second inbox item.

`LabResult` gains nothing. `ResultShare` gains `result_type`/`result_id`
(nullable), so a share made from a result can be found from the result without
disturbing the existing timeline-event shares (NG-5).

### 6.2 Interfaces

| Verb | Path | Purpose |
|---|---|---|
| POST | `/api/results/labs` | record a lab result |
| POST | `/api/results/imaging` | record an imaging study |
| GET | `/api/results/inbox` | the review queue, filtered by status/severity/patient |
| GET | `/api/results/reviews/{id}` | one review with its result |
| POST | `/api/results/reviews/{id}/review` | record the decision |
| POST | `/api/results/reviews/{id}/communicate` | share it with the patient |
| POST | `/api/results/reviews/{id}/close` | close the loop |
| POST | `/api/results/reviews/{id}/reopen` | undo a close, within 30 days |

Intake is idempotent on `(patient_id, test_name, taken_at)` for labs: a feed
that retries must not produce two potassiums and two inbox rows.

### 6.3 State machine

| From | Action | To | Guard |
|---|---|---|---|
| received | review(disposition, note) | reviewed | disposition valid; note non-empty unless disposition is `normal` |
| reviewed | communicate(message) | communicated | disposition is `needs_patient_contact` |
| reviewed | close | closed | disposition is **not** `needs_patient_contact` |
| communicated | close | closed | — |
| closed | reopen | reviewed | within 30 days |

The one guard that matters is the third: **a result whose decision was "tell the
patient" cannot be closed until they have been told.** That is the loop, and
without it the state is decoration.

### 6.4 Errors

`ResultTransitionError` → `409`, same shape as its siblings. An unknown test
name at intake is **not** an error: it is classified `normal` with `severity`
recorded as unclassified, because refusing to record a result the product does
not have a range for would lose data a clinic actually has.

### 6.5 Configuration

Classification is deterministic and lives in
`src/sephiroth/clinical/results.py`:

1. **Critical** if `sephiroth.safety.risk.LAB_RULES` fires for that test. The
   thresholds already exist there and already drive alerts — a second table of
   cutoffs would be two clinical opinions that drift apart.
2. Otherwise **abnormal** if outside the supplied reference range, or outside
   `REFERENCE_RANGES` when none is supplied.
3. Otherwise **normal**.

An imaging study takes its `severity` field directly: `critical` → critical,
`review` → abnormal, `none` → normal.

`Patient.lab_results` is updated on lab intake, so the risk engine and the
result table stop disagreeing about the current value. That write is the
narrowest fix for two representations of one fact; unifying them properly is a
bigger change than this phase.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `result_reopen_window_days` | int | 30 | how long a closed result may be reopened |

## 7. Behaviour

- **B-1** Recording a result MUST create exactly one review in `received`.
- **B-2** Recording the same lab twice MUST NOT create a second review.
- **B-3** Classification MUST be reproducible from the value and the range
  alone, with no model involved.
- **B-4** A result whose test has no known range MUST still be recorded.
- **B-5** Every `abnormal` or `critical` result MUST produce a task; a `normal`
  one MUST NOT.
- **B-6** Reviewing MUST record who, when, the disposition, and the clinician's
  note.
- **B-7** A disposition other than `normal` MUST require a non-empty note.
- **B-8** A review disposed `needs_patient_contact` MUST NOT be closable until
  it is communicated.
- **B-9** Communicating MUST create a `ResultShare` linked back to the review.
- **B-10** Closing MUST close the result's task.
- **B-11** Reopening MUST be refused outside the window.
- **B-12** Lab intake MUST update `Patient.lab_results` for that test.
- **B-13** Every read of the inbox MUST record PHI access.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-024-01 | Recording a lab creates one review, and recording it again creates none | B-1, B-2 | `tests/test_result_intake.py` |
| AC-024-02 | The same value and range always classify the same way, and an unknown test is still recorded | B-3, B-4 | `tests/test_result_classification.py` |
| AC-024-03 | An abnormal result produces a task; a normal one does not | B-5 | `tests/test_result_intake.py::TestWorkCreated` |
| AC-024-04 | Reviewing records the decision and refuses an empty note for a non-normal disposition | B-6, B-7 | `tests/test_result_loop.py::TestReview` |
| AC-024-05 | A result needing patient contact cannot be closed until it is communicated | B-8 | `tests/test_result_loop.py::TestTheLoopCannotBeShortCircuited` |
| AC-024-06 | Communicating creates a share the review points at | B-9 | `tests/test_result_loop.py::TestCommunicate` |
| AC-024-07 | Closing closes the task the result raised | B-10 | `tests/test_result_loop.py::TestClose` |
| AC-024-08 | Reopening works inside the window and is refused outside it | B-11 | `tests/test_result_loop.py::TestReopen` |
| AC-024-09 | Lab intake updates the panel the risk engine reads | B-12 | `tests/test_result_intake.py::TestThePanelStaysInStep` |
| AC-024-10 | Reading the inbox records PHI access | B-13 | `tests/test_results_inbox_router.py::TestAudit` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | classification against ranges and `LAB_RULES` | `tests/test_result_classification.py` |
| Service | intake, idempotency, task creation, panel update | `tests/test_result_intake.py` |
| Service | the five-state loop and its guards | `tests/test_result_loop.py` |
| HTTP | inbox filters, transitions, audit, role guard | `tests/test_results_inbox_router.py` |
| Frontend | the inbox's states and the close guard | `components/__tests__/result-review-card.test.tsx` |

## 10. Migration & Compatibility

One Alembic revision: `result_reviews`, plus two nullable columns on
`result_shares` and one on `tasks`' source-type constraint (`result_review`).

Additive throughout. Existing `ResultShare` rows keep their timeline-event link
and gain nulls (NG-5); existing `/api/results/shares*` endpoints are untouched,
so the patient portal and the `/results` page keep working unchanged while the
inbox is built beside them.

`src/sephiroth/clinical/results.py` joins the package added in SPEC-023, which
is already in `coverage.run.source`.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | An intake endpoint that is not an interface engine may get one pointed at it | NG-1 states it, and idempotency on `(patient, test, taken_at)` means a retrying feed is at least not destructive. A real integration is its own phase |
| 2 | Two representations of a lab result still exist (`LabResult` and `Patient.lab_results`) | Narrowed rather than solved: intake writes both, so they agree going forward. Unifying them means rewriting the risk engine's read path and backfilling timestamps that do not exist (NG-4) |
| 3 | `REFERENCE_RANGES` is a small hand-written table and will not cover a real panel | Accepted and visible: an unknown test is recorded and classified `normal` with `unclassified` severity, which is honest, rather than guessed at. It is also the signal for which ranges to add |
| 4 | Making every abnormal result a task could flood the inbox | It is the correct flood: those results are the ones that get missed today. Severity drives the SLA, so an abnormal potassium is due in hours and an abnormal HbA1c in days |
| 5 | A clinician can dispose `normal` with no note and close, which is one click from ignoring a result | Deliberate. A normal result needs no justification, and requiring one teaches people to type "ok" — which is worse than nothing, because it looks like review |
| 6 | `needs_patient_contact` blocks closing, so a patient who cannot be reached leaves the loop open | Correct behaviour, not a bug: the loop *is* open. Reopening the disposition to `action_taken` with a note recording the attempt is the honest exit |

## 12. References

- `docs/specs/SPEC-018-unified-tasks.md` — where a result's work lands.
- `docs/specs/SPEC-021-clinical-rules.md` — the thresholds reused for
  criticality.
- `docs/08-decisions/ADR-017-result-lifecycle-is-its-own-row.md`.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
