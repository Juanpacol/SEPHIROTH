# Privacy

## The honest statement

**This system is not HIPAA- or GDPR-compliant, and is not intended to be in its
current form.** Clinical text and medical images are sent to the Google Gemini
API. On the AI Studio free tier, submitted data may be used to improve Google's
models.

Use only synthetic or de-identified data.

## What that rules out

Real patient data, in any form, at any point. This is a scope boundary, not a
limitation to be worked around — see [scope.md](../00-project/scope.md).

All data in the repository is accordingly synthetic or public: Synthea-generated
patients, hand-written sample notes, public guideline excerpts, and DDInter drug
interaction data (CC BY-NC, excluded from the Docker image for its
non-commercial terms).

## What compliance would require

Documented so the gap is a known distance rather than an unknown one:

| Requirement | Current state |
|---|---|
| BAA with the model provider | None. Would mean Vertex AI, not AI Studio |
| Data residency control | None |
| Encryption at rest | Depends on the deployment's Postgres; not enforced here |
| Audit logging of PHI access | Consultation audit line exists; not PHI-grade |
| Retention and deletion policy | None |
| De-identification before egress | None — this is the substantive gap |
| Access control beyond one role | Single clinician role, no RBAC |

## Design decisions that anticipate it

Even out of scope, three choices keep the door open:

1. **Span attributes are an allow-list.** Clinical content cannot enter a trace,
   because unknown attribute keys are rejected at construction rather than
   filtered by a deny-list. Traces are the artifact most likely to be exported.
2. **`explanation` is derived, never persisted.** Reasoning trails are rebuilt on
   read from already-stored fields, so there is one less copy of clinical
   reasoning at rest.
3. **The provider abstraction is the migration path.** Vertex AI with a BAA, or a
   local model, becomes a provider implementation rather than a rewrite — which
   is the concrete privacy argument for
   [ADR-003](../08-decisions/ADR-003-model-provider-abstraction.md), separate
   from its research argument.

## Persistent memory

Long-lived storage is for **technical** state — decisions, configuration,
experiment and execution metadata, development state.

Persistent storage of sensitive clinical information is avoided unless it is
explicitly required, justified, protected and governed. None of those four
conditions currently holds, so it is not done.
