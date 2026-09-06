---
id: SPEC-023
title: The Clinical Encounter
phase: 21
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-018, SPEC-019, SPEC-022]
adrs: [ADR-016]
features: [F-095, F-096, F-097, F-098, F-099]
diagrams: []
---

# SPEC-023 — The Clinical Encounter

## 1. Summary

Adds the visit itself. Everything around it already exists — the appointment
that schedules it, the alerts that interrupt it, the tasks that follow it, the
note that records it — and the middle was missing: a clinician had nowhere to
put what happened in the room.

An `Encounter` holds the vitals, the reason, the note, the orders and the
instructions for one visit; it is `draft` while being written and `signed` once
the clinician commits. Signing is the moment everything downstream fires: the
note reaches the chart, the orders become tasks, the timeline updates.

## 2. Motivation

`Appointment` says a visit was booked. `ClinicalNote` says something was
written afterwards. Nothing joins them, so the actual work of a consultation
happens in a clinician's head and lands in the system as a wall of free text,
if it lands at all.

Concretely, four things have no home:

- **Vitals.** There is no place for a blood pressure. `Patient.lab_results`
  holds a `bp` string that the risk engine reads, so a clinic that records
  vitals is overwriting a lab field with something that is not a lab.
- **Orders.** "Repeat the potassium in a week" is work, and SPEC-018 built the
  inbox for exactly that kind of work — but nothing creates a task from a
  decision made in the room, so it survives only if the clinician remembers to
  file it separately.
- **Patient instructions.** The one output the patient actually leaves with.
- **The reason the visit happened**, in a form anything can read. `Appointment.reason`
  is a 200-character string typed at booking, often by the front desk.

And the note itself is the highest-value place for AI in the product and the
one place it currently is not: SPEC-022 made a local model the default, so the
privacy objection to drafting from dictation no longer applies. A note drafted
from what the clinician said, then edited and signed by them, is minutes back
per patient — the whole premise of this plan.

### A deliberate divergence from the phase plan

The plan for this phase said note drafting must go **through the existing
`PendingAction` approval gate**, so nothing is saved without review. The
guarantee is right; the mechanism is wrong, and adopting it would weaken what
it is trying to protect.

`PendingAction` exists for **messages sent to a patient**, where approval is
consent to transmit — `task_adapters.py` refuses to let a clinician close an
approval task for exactly that reason. A note draft is not transmitted to
anyone. Routing it through the same queue would mean an approvals inbox mixing
"send this message to Ana" with "save this paragraph", where a single Approve
button means two different acts.

The encounter's own `draft` → `signed` transition is the stronger guarantee, not
a weaker one: an unsigned note **cannot** reach the chart, the timeline, or the
patient, and signing records who committed to it and when. An approval row can
be approved by someone who never read it; a signature is attached to the
clinical content it signs. Same requirement — nothing saved without review —
enforced where the content actually lives. See ADR-016.

## 3. Goals

- **G-1** One record per visit, holding what happened in the room.
- **G-2** No clinical content reaches the chart unreviewed.
- **G-3** A decision made in the room becomes tracked work without being typed
  twice.
- **G-4** The model drafts; the clinician decides. Losing the model costs the
  drafting convenience and nothing else.
- **G-5** Opening an encounter shows what the clinician needs before the
  patient sits down.

## 4. Non-Goals

- **NG-1** No billing, coding, or ICD/CPT mapping. That is a different product
  surface with its own correctness bar, and guessing at codes is worse than
  leaving them out.
- **NG-2** No audio capture or speech-to-text. The note is drafted from text
  the clinician types or pastes. Dictation is a client-side capability that can
  feed this endpoint later without changing it.
- **NG-3** No prescribing. An order here is a reminder to a human, not a
  transmission to a pharmacy.
- **NG-4** No structured problem list or diagnosis coding beyond free-text
  extraction into `Encounter.assessment`. `Patient.conditions` stays as it is.
- **NG-5** No amendment history beyond a single `amended_at`/`amendment_reason`
  and the immutable original. A full versioned note is a real requirement in a
  real EHR and a large one; this records that an amendment happened rather than
  pretending it did not.
- **NG-6** No encounter type taxonomy. One shape, with a `specialty` that only
  chooses a template.

## 5. Definitions

- **Encounter** — one clinical visit's record: vitals, reason, note, orders,
  instructions.
- **Signing** — the clinician's commitment. Irreversible into `draft`; a signed
  encounter can only be amended, never un-signed.
- **Order** — an instruction decided in the room (a lab, an imaging study, a
  referral, a follow-up), which becomes a task on signing.
- **Pre-visit brief** — a read-only assembly of what is already known about
  this patient, computed on request, never stored.

## 6. Contracts

### 6.1 Types

`data/schemas/__init__.py`:

**`encounters`**

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `id` | String(36) | yes | — | PK |
| `patient_id` | FK patients | yes | — | |
| `clinician_id` | FK users | yes | — | who is seeing the patient |
| `appointment_id` | FK appointments | no | null | nullable: a walk-in has no booking |
| `specialty` | String(40) | yes | `general` | chooses a template only |
| `status` | String(12) | yes | `draft` | `ck_encounter_status`: draft/signed/amended |
| `chief_complaint` | EncryptedText | yes | `""` | |
| `vitals` | EncryptedJSON | yes | `{}` | keys from `VITAL_SPECS` |
| `subjective` | EncryptedText | yes | `""` | |
| `objective` | EncryptedText | yes | `""` | |
| `assessment` | EncryptedText | yes | `""` | |
| `plan` | EncryptedText | yes | `""` | |
| `patient_instructions` | EncryptedText | yes | `""` | what the patient leaves with |
| `note_source` | String(10) | yes | `clinician` | `ck_encounter_note_source`: clinician/llm/template |
| `note_model` | String(64) | no | null | the model that drafted, when one did |
| `started_at` | DateTime | yes | now | |
| `signed_at` | DateTime | no | null | `ck_encounter_signed_requires_signer` |
| `signed_by` | FK users | no | null | same constraint |
| `amended_at` | DateTime | no | null | |
| `amendment_reason` | String(300) | yes | `""` | non-empty when `amended_at` is set |
| `clinical_note_id` | FK clinical_notes | no | null | set on signing |
| `created_at` / `updated_at` | DateTime | yes | now | |

Indexes: `(patient_id, started_at desc)`, `(clinician_id, status)`,
`(status, started_at)`, unique on `appointment_id` where not null — one
encounter per booking.

Four narrative columns rather than one, because SOAP is what a clinician
already thinks in and what every template renders into; one `note` blob would
make the model's draft and the clinician's edit fight over the same field.

**`encounter_orders`**

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `id` | String(36) | yes | — | PK |
| `encounter_id` | FK encounters | yes | — | cascade delete with a draft |
| `kind` | String(20) | yes | — | `ck_encounter_order_kind`: lab/imaging/referral/followup/medication |
| `detail` | EncryptedText | yes | — | non-empty |
| `due_in_days` | Integer | no | null | null = no deadline |
| `task_id` | FK tasks | no | null | set on signing |
| `created_at` | DateTime | yes | now | |

A child table rather than a JSON list, for the same reason `task_events` is:
"which orders were never acted on" has to be answerable by query.

### 6.2 Interfaces

`platform/api/routers/encounters.py`, mounted at `/api/encounters`, clinician-only
at router level.

| Verb | Path | Purpose |
|---|---|---|
| POST | `/api/encounters` | start one (optionally from an appointment) |
| GET | `/api/encounters` | list, filtered by patient/status/clinician |
| GET | `/api/encounters/{id}` | one, with its orders |
| PATCH | `/api/encounters/{id}` | edit any draft field |
| POST | `/api/encounters/{id}/orders` | add an order |
| DELETE | `/api/encounters/{id}/orders/{order_id}` | remove one, draft only |
| POST | `/api/encounters/{id}/draft-note` | ask the model to draft from free text |
| POST | `/api/encounters/{id}/sign` | commit |
| POST | `/api/encounters/{id}/amend` | reopen a signed encounter with a reason |
| GET | `/api/patients/{id}/pre-visit` | the brief |

`POST /draft-note` takes `{"transcript": str, "specialty"?: str}` and returns
the four SOAP fields **without persisting them**. The clinician sees the draft
next to their own text and applies it with a `PATCH` — so an LLM draft never
reaches even the draft record without a human action.

### 6.3 State machine

| From | Action | To | Guard |
|---|---|---|---|
| draft | sign | signed | at least one narrative field non-empty; signer is the encounter's clinician |
| signed | amend(reason) | amended | reason non-empty; within 30 days |
| amended | sign | signed | same as draft |
| any | delete | — | **draft only**, and only by its own clinician |

`signed` and `amended` both mean "in the chart". The distinction is provenance:
`amended` says the signed content was changed after the fact, which is a thing
a reader must be able to see.

There is no un-sign. A signed note is a clinical record; the correction
mechanism is an amendment that says so.

### 6.4 Errors

- `EncounterTransitionError` → HTTP `409`, same shape as `TaskTransitionError`.
- Signing an empty encounter → `409`, not `422`: the request is well-formed and
  the state forbids it.
- `PHINotAllowedError` from `/draft-note` → `503` with the template draft still
  returned (see B-9).

### 6.5 Configuration

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `encounter_amend_window_days` | int | 30 | how long a signed encounter may be amended |

Vital ranges are code, not settings — the same reasoning SPEC-021 §6.5 gives
for lab thresholds.

## 7. Behaviour

- **B-1** An encounter MUST start in `draft` and MUST be editable only while
  `draft` or `amended`.
- **B-2** Signing MUST record who signed and when, and MUST be refused when
  every narrative field is empty.
- **B-3** Signing MUST create exactly one `ClinicalNote` carrying the rendered
  note, linked back by `clinical_note_id`.
- **B-4** Signing MUST create one task per order, with `source_type="encounter"`
  and a `dedupe_key` of `encounter:{encounter_id}:{order_id}`, so signing twice
  cannot double-file.
- **B-5** Signing MUST be idempotent: a second sign of a signed encounter
  changes nothing and creates nothing.
- **B-6** An order's `due_in_days` MUST set its task's `due_at`; without one the
  task takes the severity SLA (SPEC-018).
- **B-7** Vitals MUST accept only known keys, and MUST reject a value outside
  its physiological bound rather than storing it.
- **B-8** A vital outside its *clinical* range MUST be reported as a finding on
  read, and MUST NOT block saving — a real blood pressure of 210/120 is the
  case the feature exists for.
- **B-9** `/draft-note` MUST return a deterministic template draft when the
  model is unavailable or refuses, never an error with no draft.
- **B-10** A drafted note MUST NOT be persisted by `/draft-note`; only a
  subsequent `PATCH` writes it.
- **B-11** `note_source` MUST record whether the persisted narrative came from
  a model, and `note_model` which one.
- **B-11a** A drafted section whose vocabulary is largely absent from the
  clinician's own text MUST be reported in `added_content`, so the UI can mark
  which sections to read hardest.
- **B-12** Amending MUST require a non-empty reason and MUST be refused outside
  the window.
- **B-13** The pre-visit brief MUST be computed on read and MUST NOT persist
  anything.
- **B-14** Every read of an encounter MUST record a `PhiAccessLog` row.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-023-01 | A draft is editable, a signed one is not, and signing records signer and time | B-1, B-2 | `tests/test_encounter_model.py`, `tests/test_encounters_router.py::TestLifecycle` |
| AC-023-02 | Signing an encounter with nothing written is refused with 409 | B-2 | `tests/test_encounters_router.py::TestLifecycle` |
| AC-023-03 | Signing creates one note and one task per order; signing twice creates no more | B-3, B-4, B-5 | `tests/test_encounter_signing.py` |
| AC-023-04 | An order with `due_in_days` produces a task due then; without one it takes the SLA | B-6 | `tests/test_encounter_signing.py::TestOrderDeadlines` |
| AC-023-05 | Unknown vital keys and physiologically impossible values are rejected; clinically abnormal ones are saved and flagged | B-7, B-8 | `tests/test_vitals.py` |
| AC-023-06 | With the model down, `/draft-note` still returns a usable template draft | B-9 | `tests/test_encounter_note_drafting.py` |
| AC-023-07 | `/draft-note` persists nothing; the record changes only after a PATCH, which records the source | B-10, B-11 | `tests/test_encounter_note_drafting.py::TestNothingIsPersisted` |
| AC-023-11 | A section the model wrote rather than reorganised is reported in `added_content` | B-11a | `tests/test_encounter_note_drafting.py::TestAddedContentIsFlagged` |
| AC-023-08 | Amending needs a reason, is refused after the window, and leaves the encounter editable again | B-12 | `tests/test_encounters_router.py::TestAmendment` |
| AC-023-09 | The pre-visit brief assembles prior visits, open tasks, results, meds and allergies without writing anything | B-13 | `tests/test_pre_visit_brief.py` |
| AC-023-10 | Reading an encounter records PHI access | B-14 | `tests/test_encounters_router.py::TestAudit` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | vital validation and range flags, SOAP template rendering | `tests/test_vitals.py`, `tests/test_encounter_templates.py` |
| Model | constraints, encrypted round-trip, cascade | `tests/test_encounter_model.py` |
| Service | signing, order-to-task, idempotency | `tests/test_encounter_signing.py` |
| HTTP | lifecycle, guards, audit, amendment | `tests/test_encounters_router.py` |
| Degradation | model down, PHI refused | `tests/test_encounter_note_drafting.py` |
| Read model | the brief | `tests/test_pre_visit_brief.py` |
| Frontend | the draft panel's two promises, and blood pressure as one field | `components/__tests__/encounter-note-draft.test.tsx`, `encounter-vitals-form.test.tsx` |

## 10. Migration & Compatibility

One Alembic revision, purely additive: two new tables, no column on any
existing table is altered. `ClinicalNote` and `Appointment` are untouched —
the link is held from the encounter's side, so a deployment that never creates
an encounter behaves exactly as it does today.

`tasks.source_type` gains `encounter` in its check constraint, which is a
constraint replacement rather than a new column.

`src/sephiroth/clinical/` is a new package and is added to
`coverage.run.source` in this PR, per the charter.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | **A small local model does not obey "do not add information."** Observed, not hypothesised: running this phase's own prompt against `qwen2.5:3b` on "cefalea de tres días, PA 210/120, inicio losartán" produced an assessment of "Hipertensión arterial" and a plan including a brain scan. Both plausible; neither in the text | Three layers, none of which is the prompt. The signature is the guarantee (ADR-016) — nothing reaches the chart unread. `added_content` (B-11a) marks the sections whose vocabulary is largely absent from the source, so review is aimed rather than uniform. And `note_source` is persisted, so a later reader knows a model wrote the first version. The prompt still says it, and is treated as a preference rather than a control |
| 1b | `added_content` is word overlap, not meaning | Over-flags a heavily paraphrased section, which costs a second look; under-flags a fabrication assembled from the source's own words. It is an aid to review, never a substitute — the same posture as ADR-006's low-overlap downgrade in claim verification |
| 2 | Vitals in `vitals` JSON are not queryable the way columns would be | Accepted, matching `Patient.lab_results`. A trend view is a later phase's problem and would be built on a normalised table then, not by columns nobody reads now |
| 3 | Orders create tasks only on signing, so a draft abandoned mid-visit files nothing | Deliberate. A task created from an unsigned decision is work nobody committed to, and the inbox's value is that everything in it is real |
| 4 | The 30-day amendment window is arbitrary | It matches the task reopen window (SPEC-018), so a clinician meets one number rather than two. Configurable for a deployment that must match a local retention rule |
| 5 | NG-5's single-amendment record is thin for a real EHR | Stated rather than papered over. The original narrative is preserved on the `ClinicalNote` created at signing, so the pre-amendment text is not lost even though the diff is not modelled |
| 6 | `/draft-note` sends the clinician's free text to the model, which is patient content | It is a PHI seam and is gated as one (SPEC-022 §6.5, ADR-015). On the default local provider nothing leaves the machine |
| 7 | One encounter per appointment may be wrong for a visit that spans two bookings | Accepted for now; the unique index is on `appointment_id`, not on `(patient_id, day)`, so a walk-in or a second unlinked encounter is always possible |

## 12. References

- `docs/specs/SPEC-018-unified-tasks.md` — where orders land.
- `docs/specs/SPEC-022-local-ai.md` — why drafting locally is now the default.
- `docs/08-decisions/ADR-016-signing-is-the-review-gate.md` — why not
  `PendingAction`.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
