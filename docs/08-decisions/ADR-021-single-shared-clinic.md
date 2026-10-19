# ADR-021 — One shared clinic

**Status:** Accepted · **Date:** 2026-10-19

## Context

Every clinician account sees every patient. The patient list, the dashboard,
the results inbox and the review queues are not filtered by the clinician who
asks: they only require the clinician role (`require_clinician`). That is the
model of a single clinic, and it is the model the product was built around.

It is also a decision nobody wrote down, and one thing separated it from being
a hole: who can create a clinician account. `allow_bootstrap_registration`
defaulted to open, and production stayed closed only because `render.yaml` said
so. A missing or deleted variable in the Render dashboard would have opened
`POST /api/auth/register` to anyone, who could then read every patient.

## Decision

1. **The model is one shared clinic.** All clinicians see all patients and all
   consultations. Nothing is isolated per clinician or per organisation.
2. **That is acceptable today** because the data in every deployment is
   synthetic, accounts in staging and production are created only by a clinician
   who already exists, and every read of a patient's chart is written to the
   access log (`phi_access_log`, and `review_access_log` for the review token).
3. **Open registration is closed by the code, not by a deployment file.**
   `allow_bootstrap_registration` defaults to `false` in `staging` and
   `production` and to `true` in `development` and `test`. An explicit value
   still wins, and `render.yaml` keeps stating `false`; a test fails if it stops.
4. **Production holds synthetic data only.** Real patient data does not enter a
   deployment on this model.

## Revisit before any of these

The model has to change *before*, not after:

- real (non-synthetic) patient data enters a deployment;
- a second clinic or organisation uses the same installation;
- external clinicians are invited who should not see every patient;
- `AI_ALLOW_PHI` is turned on, sending patient content to a remote model.

Changing it means isolating data per clinic: a `clinic_id` on patients,
appointments, alerts, consultations and the rest, a filter on every query and
endpoint, a migration for the existing rows, and probably row-level security in
Postgres (`ADR-012`). That is a large change across the backend, and it is
deliberately not built until one of the triggers above is real, so its
requirements come from a real case.

## Consequences

- A fresh staging or production database has no way to create its first
  account through the API. The first clinician is created out of band (directly
  in the database), or `ALLOW_BOOTSTRAP_REGISTRATION=true` is set for that one
  boot and put back to `false` straight after. No runbook covers this yet.
- Development and tests are unchanged: registration stays open, so
  `scripts/smoke_test.sh` and the suite need no bootstrap step.
