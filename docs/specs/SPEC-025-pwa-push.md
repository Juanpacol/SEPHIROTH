---
id: SPEC-025
title: PWA and Web Push
phase: 23
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-017, SPEC-020]
adrs: [ADR-018]
features: [F-104, F-105, F-106, F-107]
diagrams: []
---

# SPEC-025 — PWA and Web Push

## 1. Summary

Makes the product installable and lets it reach a clinician who is not looking
at it. A critical alert that escalates at 3am currently writes a row nobody
sees until somebody opens a browser tab.

The payload never contains patient content. That is the constraint the whole
design is arranged around, and it is enforced by a table of fixed strings and a
regression test, not by care at each call site.

## 2. Motivation

`Notification` is the entire delivery mechanism, and its own docstring says so:
*"no email/SMS/push channel exists in this codebase"*. The bell icon polls. So
every piece of automation this plan has built — the escalation that fires when
a critical alert goes unreviewed, the reminder, the result that needs telling —
ends at a row in a table, waiting for someone to already be looking.

That is the wrong shape for the two cases it exists for. An alert escalates
*because* nobody has acted on it, and a reminder is useful *because* the person
is not thinking about the appointment.

And the application cannot be installed. SPEC-017 made it usable on a phone —
bottom nav, touch targets, cards below `md` — and a clinician still reaches it
by typing a URL into a browser. `contact_preference` has been validated and
stored since phase 8 with `'in_app'` as its only legal value, described in the
code as *"the only channel that exists ... reserved for 'email'/'sms'"*.

## 3. Goals

- **G-1** A clinician can be reached when the application is closed.
- **G-2** No patient content leaves in a push payload, ever.
- **G-3** Push is opt-in per device, from an explicit action.
- **G-4** A dead subscription stops being retried and says why.
- **G-5** The application is installable, and offline behaviour is
  conservative enough to be safe in a clinic.

## 4. Non-Goals

- **NG-1** No email or SMS. Both need an account, a sender identity and a
  deliverability story; web push needs none of those, which is why it is first.
- **NG-2** No offline writes and no background sync. A queued clinical write
  that lands hours later, against a chart that has moved, is a class of bug
  worth refusing outright. Offline is read-only shell and static assets.
- **NG-3** No caching of `/api/*`. Clinical data must never be served stale,
  and responses are bound to an `Authorization` header, so caching them is a
  leak between accounts on a shared device.
- **NG-4** No push for the patient portal in this phase. The same machinery
  will serve it; the notification vocabulary and the consent question are
  different, and shipping half of that reasoning is worse than shipping none.
- **NG-5** No notification grouping, actions, or rich media. A title, a body,
  a URL.

## 5. Definitions

- **Subscription** — one browser on one device, identified by the endpoint URL
  the push service issues.
- **Delivery** — one attempt to send one notification to one subscription. Has
  its own row, so a failure is attributable to a device rather than to a user.
- **Safe copy** — the fixed string sent for a notification type, chosen so that
  it is true of every notification of that type and specific to none.

## 6. Contracts

### 6.1 Types

**`push_subscriptions`**

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `id` | String(36) | yes | — | PK |
| `user_id` | FK users | yes | — | |
| `endpoint` | String(500) | yes | — | **unique** — one row per browser |
| `p256dh` | String(200) | yes | — | the browser's public key |
| `auth` | String(100) | yes | — | the shared auth secret |
| `user_agent` | String(200) | yes | `""` | so a person can tell their devices apart |
| `failure_count` | Integer | yes | `0` | consecutive failures |
| `disabled_at` | DateTime | no | null | soft delete; a gone endpoint is kept, not deleted |
| `last_success_at` | DateTime | no | null | |
| `created_at` | DateTime | yes | now | |

**`push_deliveries`**

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `id` | String(36) | yes | — | PK |
| `subscription_id` | FK push_subscriptions | yes | — | cascade |
| `notification_id` | FK notifications | yes | — | what it is delivering |
| `status` | String(10) | yes | `pending` | `ck_push_delivery_status`: pending/sent/failed/dropped |
| `attempts` | Integer | yes | `0` | |
| `send_after` | DateTime | yes | now | backoff, same shape as a workflow step |
| `last_error` | String(200) | yes | `""` | |
| `created_at` / `updated_at` | DateTime | yes | now | |

Unique on `(subscription_id, notification_id)` — one delivery per device per
notification, so a retried enqueue cannot buzz a phone twice.

`Notification` is unchanged. Its `dedupe_key` uniqueness stays the single
source of truth for "already delivered" (§6.3).

### 6.2 Interfaces

| Verb | Path | Purpose |
|---|---|---|
| GET | `/api/push/key` | the VAPID public key the browser needs to subscribe |
| POST | `/api/push/subscriptions` | register this browser |
| DELETE | `/api/push/subscriptions` | unregister it (by endpoint) |
| GET | `/api/push/subscriptions` | this user's devices, for the settings page |

`NotificationChannel.send`'s signature **does not change** — six call sites
depend on it — and gains one optional keyword, `url`, for where a tap should
land.

### 6.3 State machine

A delivery is `pending` → `sent`, or `pending` → `failed` after three
attempts, or `pending` → `dropped` when its subscription is gone.

The interesting transition is the subscription's: a `404` or `410` from the
push service means the browser threw the subscription away, so the row is
disabled immediately and its pending deliveries are dropped. There is no
retrying that; the endpoint will never work again.

**Enqueueing is gated on the in-app write.** `CompositeChannel` calls the
in-app channel first, and if it returns `False` — meaning `dedupe_key` was
already used — nothing is enqueued. One source of truth for "already
delivered", rather than two mechanisms that agree until they do not.

### 6.4 Errors

Push send failures are classified, not retried uniformly:

| Response | Meaning | Action |
|---|---|---|
| 201/200 | delivered | `sent`, reset `failure_count` |
| 404, 410 | subscription gone | disable it, drop its pending deliveries |
| 413 | payload too large | `failed` immediately — a retry sends the same bytes |
| 429, 5xx | transient | retry with backoff, three attempts |
| anything else | unknown | retry, three attempts |

A send never raises into the tick. The tick's job is to keep running.

### 6.5 Configuration

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `vapid_public_key` | str | `""` | empty disables push entirely |
| `vapid_private_key` | str | `""` | same |
| `vapid_subject` | str | `mailto:ops@sephiroth.local` | contact for the push service |
| `push_max_attempts` | int | 3 | |
| `push_batch_size` | int | 50 | deliveries per tick |

With no keys configured, `CompositeChannel` is exactly `InAppChannel` and
nothing else changes. That is the state every existing deployment starts in.

`AutomationMemory._KEY_SPECS` gains `push_enabled` (bool) and `notify_types`
(list of notification types). `contact_preference` relaxes from `'in_app'` to
`{in_app, web_push, both}`.

## 7. Behaviour

- **B-1** A push payload MUST contain only `{title, body, url, tag,
  notification_id}`, with `title`/`body` drawn from a fixed table keyed on
  notification type.
- **B-2** A notification whose `message` contains a patient's name MUST produce
  a payload that does not.
- **B-3** Nothing MUST be enqueued when the in-app write was a duplicate.
- **B-4** Nothing MUST be enqueued for a user with no enabled subscription, or
  with `push_enabled` off, or for a type not in their `notify_types`.
- **B-5** Sending MUST happen from the tick, never inside the caller's
  transaction.
- **B-6** A `404`/`410` MUST disable the subscription and drop its pending
  deliveries.
- **B-7** A transient failure MUST retry with backoff, at most
  `push_max_attempts` times.
- **B-8** A send that raises MUST NOT propagate into the tick.
- **B-9** With no VAPID keys, every existing behaviour MUST be unchanged.
- **B-10** The service worker MUST NOT cache any `/api/*` response.
- **B-11** Permission MUST be requested only from an explicit user action.
- **B-12** A subscription MUST belong to exactly one user, and re-registering
  an endpoint under a different user MUST move it.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-025-01 | A payload built from a notification naming a patient contains no patient content | B-1, B-2 | `tests/test_push_payload.py` |
| AC-025-02 | A duplicate in-app write enqueues nothing | B-3 | `tests/test_push_channel.py::TestEnqueueing` |
| AC-025-03 | Nothing is enqueued for a user who has not opted in, or for a muted type | B-4 | `tests/test_push_channel.py::TestOptIn` |
| AC-025-04 | Deliveries are sent from the tick, and a caller's transaction makes no HTTP call | B-5 | `tests/test_push_dispatch.py::TestItSendsFromTheTick` |
| AC-025-05 | 404/410 disables the subscription and drops its pending deliveries | B-6 | `tests/test_push_dispatch.py::TestAGoneSubscription` |
| AC-025-06 | A transient failure retries with backoff and gives up after the cap | B-7 | `tests/test_push_dispatch.py::TestTransientFailure` |
| AC-025-07 | A send that raises leaves the tick running | B-8 | `tests/test_push_dispatch.py::TestNothingReachesTheTick` |
| AC-025-08 | With no VAPID keys the channel is the in-app channel and nothing is enqueued | B-9 | `tests/test_push_channel.py::TestDisabled` |
| AC-025-09 | Registering an endpoint twice keeps one row; registering under another user moves it | B-12 | `tests/test_push_router.py` |
| AC-025-10 | The declared policy caches no API response, and the built worker contains no "apis" cache | B-10 | `platform/frontend/lib/__tests__/service-worker-policy.test.ts` |
| AC-025-11 | The toggle asks for permission only on a click, and handles denied | B-11 | `components/__tests__/push-toggle.test.tsx` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | payload construction and its PHI guarantee | `tests/test_push_payload.py` |
| Service | enqueueing, opt-in, disabled state | `tests/test_push_channel.py` |
| Service | dispatch, failure classification, backoff | `tests/test_push_dispatch.py` |
| HTTP | subscription lifecycle, ownership | `tests/test_push_router.py` |
| Frontend | the toggle's three permission states | `components/__tests__/push-toggle.test.tsx` |
| Frontend | the caching policy is a value a test can read | `lib/__tests__/service-worker-policy.test.ts` |

## 10. Migration & Compatibility

One Alembic revision: two new tables. Nothing existing is altered.

`pywebpush>=2.0` is a new dependency (with `py-vapid` and `http-ece`). It is
synchronous, so sends run in `asyncio.to_thread` — acceptable because they only
run from the tick, never in a request.

`@serwist/next` and `serwist` are new frontend dependencies. The generated
service worker precaches the app shell; the `push` and `notificationclick`
handlers are hand-written, because they are the part that carries the
guarantees.

**A deployment that sets no VAPID keys is bit-for-bit unchanged.** No
subscriptions can be created, `CompositeChannel` degrades to `InAppChannel`,
and the tick's dispatch step finds nothing.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Push latency is up to one tick (5 minutes) | Stated in the dispatcher's docstring and accepted for reminders and escalations. It would be wrong for anything conversational, which is why NG-4 keeps the patient portal out |
| 2 | A fixed-string payload tells a clinician less than a specific one | Deliberate, and the trade this phase exists to make. A lock screen is visible to whoever is holding the phone; the notification says a critical alert needs review, and the application says which |
| 3 | `pywebpush` is synchronous | Wrapped in `asyncio.to_thread`, and only ever called from the tick |
| 4 | VAPID keys in settings are a new secret to manage | Same posture as `JWT_SECRET` and `PHI_ENCRYPTION_KEY`: empty disables the feature rather than failing |
| 5 | A service worker that caches wrongly could serve one clinician another's data | **Found, not hypothesised.** Serwist's `defaultCache` caches same-origin `GET /api/*` for 24 hours in a cache named "apis" -- read out of the generated worker while building this phase. Adopting it would have shipped exactly this leak. The runtime caching list is now declared in `lib/service-worker-policy.ts` rather than inherited and filtered, so there is no `/api` rule to remove, and the test asserts on both the declaration and the built worker |
| 6 | Safari's push support requires the app to be installed to the home screen | Accepted. The toggle reports "not supported" rather than failing, and the install prompt is the same PWA machinery |
| 7 | A clinician who denies permission cannot be asked again by the page | Browser behaviour, not ours. The toggle explains how to change it in browser settings rather than pretending a retry will work |

## 12. References

- `docs/specs/SPEC-017-interface-foundations.md` — the responsive shell this
  makes installable.
- `docs/08-decisions/ADR-018-push-payloads-carry-no-phi.md`.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
