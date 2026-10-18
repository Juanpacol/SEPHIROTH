# Consultation review endpoint (AB#15)

Read-only view of what happened in a consultation: which model answered, whether a fallback served it, which tools ran, what the verifier said. For a reviewer who is not the clinician and has no database or log access. Source: `platform/api/routers/review.py`.

## Enable

1. Generate a token: `openssl rand -hex 32`.
2. Set it as `REVIEW_TOKEN` in the Render dashboard (never commit it). Unset means every `/api/review/*` route answers **404**: nothing is exposed by default. In `staging`/`production` it must be 32 characters or more or the app fails to boot.
3. Rotate: set a new value and redeploy. The old token stops working at once. The audit log tells tokens apart by a fingerprint, so reads before and after a rotation stay distinguishable.

Send it as the `X-Review-Token` header. It is not a user JWT and opens no other route.

## Routes (GET only; any other method is 405)

| Route | Returns |
|---|---|
| `/api/review/consultations` | newest first: `trace_id`, date, agents, provider, model, `fallback`, status, risk, latency, patient pseudonym. Filters: `since`, `until`, `fallback`, `status` (`answer`/`partial`/`abstain`), `limit` (max 100), `offset`. |
| `/api/review/consultations/{trace_id}` | the above plus de-identified `query` and `answer`, every model call with its fallback reason, tool names and outcome, citation counts, claims with their verdict, abstention, tokens, cost, failure categories. |

`trace_id` is the id shown in the app under "How this answer was produced" and in the Render log lines (`trace_id=...`).

`fallback` and `status` are filtered after reading, so a rare filter may stop at 1000 rows: the list then says `"complete": false`. Narrow it with `since`/`until`.

Rate limit: 60 requests a minute. An unknown `trace_id` is a plain 404.

## What is removed

- The patient is a stable pseudonym (`pt_...`, keyed by `PHI_ENCRYPTION_KEY`): the same patient always gets the same one. The clinician is not named.
- Tool arguments and tool results are never returned, only tool name, agent, outcome and latency.
- Free text (`query`, `answer`, claim text) has the patient's own name parts and record number removed wherever they appear, plus emails, URLs, phone numbers, long digit runs and dates.

This is best-effort, not a guarantee: a name that is not the patient's, or an identifier in an unusual shape, can get through. Treat the token like access to clinical data and use synthetic data unless the deployment is cleared for real patients.

## Audit

Every read writes a row to `review_access_log` (token fingerprint, route, method, `trace_id`, filters), including reads of a trace that does not exist. A request with a wrong token is rejected before anything is written.
