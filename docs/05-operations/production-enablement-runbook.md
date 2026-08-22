# Production enablement runbook — SPEC-009 workflow engine

**Audience:** whoever has access to the Render dashboard and the cron-job.org
account for this deployment. These are the operator's own accounts — nothing
in this repo or CI can do these steps; they're deliberately manual.

**Why this order matters:** `Settings._check_tick_token` (`platform/core/config.py`)
fails the app's boot in `production` if `ENABLE_WORKFLOW_ENGINE=true` and
`INTERNAL_TICK_TOKEN` is unset or under 32 characters. Doing the steps out of
order takes production down; doing them in this order never does.

## Step 1 — Set `INTERNAL_TICK_TOKEN` (engine still off)

1. Generate a strong token:
   ```bash
   openssl rand -hex 32
   ```
2. Render dashboard → the `sephiroth-api` service → **Environment** → add/edit
   `INTERNAL_TICK_TOKEN` with that value.
3. Save. Render redeploys automatically on an env var change — this is safe:
   `ENABLE_WORKFLOW_ENGINE` is still `false` (`render.yaml`), so the token
   isn't checked yet and isn't used yet.
4. Confirm the redeploy finished and `/health/ready` still returns
   `{"status":"ready",...}`.

## Step 2 — Flip `ENABLE_WORKFLOW_ENGINE` to `true`

1. Render dashboard → same service → **Environment** → edit
   `ENABLE_WORKFLOW_ENGINE` → `true`.
2. Save, let it redeploy.
3. Confirm `/health/ready` is still `ready` — if the boot instead fails with
   a tick-token error, Step 1 wasn't actually saved; go back and fix it
   before proceeding.
4. Sanity-check the internal tick endpoint responds to a real request:
   ```bash
   curl -s -X POST https://sephiroth-api.onrender.com/internal/tick \
     -H "X-Internal-Token: <the token from Step 1>"
   ```
   Expect a JSON tick summary (`{"status":"ok","tick_id":...,"claimed":0,...}`)
   — `claimed: 0` is correct right now, since no workflow exists yet
   (Step 4 creates the first one).

## Step 3 — Point an external cron at `/internal/tick`

1. [cron-job.org](https://cron-job.org) (free tier) → create a new cron job:
   - URL: `https://sephiroth-api.onrender.com/internal/tick`
   - Method: `POST`
   - Header: `X-Internal-Token: <the token from Step 1>`
   - Schedule: every 5 minutes
2. Save and let it fire once. Check cron-job.org's execution log shows a
   `200` response.
3. Side benefit: this also keeps the free Render instance from spinning down
   on idle, since it now gets a request every 5 minutes.

## Step 4 — Seed the first real workflow and confirm a tick actually does something

Nothing has enrolled any workflow yet — the engine is live but idle. The
simplest first real workflow is `alert_refresh` (Phase 9), which needs no
patient data:

1. Log in as a real clinician (the smoke-test account or your own) and hit
   any endpoint that touches `sephiroth.safety.alerts` — e.g. viewing
   `/api/patients` triggers alert generation for patients with risk flags,
   which is what emits the escalation workflow.
2. Wait for the next cron tick (≤5 minutes), or trigger one manually with
   the same `curl` command as Step 2.
3. Check `GET /api/dashboard/automation` (as a clinician) — `workflows.total`
   should now be ≥ 1, and `steps` should show at least one row that isn't
   `pending` anymore (either `succeeded`, `running`, or scheduled for later).
4. If you want to see the full loop end-to-end: create a follow-up plan on
   any patient (`/patients/[id]` → Follow-up plan card), wait for the next
   tick or two (day-3/7/30 steps aren't due immediately — the plan enrolling
   is itself the thing to confirm), and separately verify the approvals flow
   with a `PendingAction` created directly (see `tests/test_approval_send_path.py`
   for the exact shape) if you want to see a real send without waiting days.

## Rollback

If anything looks wrong after Step 2:
1. Render dashboard → flip `ENABLE_WORKFLOW_ENGINE` back to `false`, save,
   redeploy. The engine stops being invoked; nothing else in the app depends
   on it (SPEC-009's whole design point — it's additive).
2. cron-job.org → pause or delete the cron job.
3. No data is lost by doing this — `Workflow`/`WorkflowStep` rows just stop
   advancing until the engine is re-enabled.

## What this does *not* cover

- Migration drift verification (Phase D of the finishing-the-automation-layer
  plan) — already done and merged; this runbook assumes `alembic upgrade head`
  is current on the live database, which `init_db()` already guarantees on
  every boot.
- Rate limiting on `/internal/tick` — the shared secret is the only control
  today (documented as a known limitation in the Phase B security-fix
  commit). If the token leaks, rotate it in Render's dashboard (Step 1,
  repeated) and update the cron-job.org header to match.
