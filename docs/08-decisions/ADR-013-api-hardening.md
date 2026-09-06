# ADR-013 — API hardening: rate limiting, security headers, HTTPS posture

**Status:** Accepted · **Date:** 2026-09-04

## Context

A security audit (19-point checklist) flagged missing rate limiting on
auth/consult endpoints, no account lockout, no security response headers,
and no application-level HTTPS enforcement.

## Decisions

**Rate limiting + lockout.** `slowapi` (`platform/core/rate_limit.py`), a
global default (300/min) plus tighter per-route limits on
`/login`/`/login/mfa` (10/min), `/register`/`/portal/claim` (10/hour),
`/password-reset/request` (5/hour), and `/api/agents/consult*` (20/hour,
keyed by authenticated user via `key_by_user_or_ip` rather than IP — a
clinic's shared IP shouldn't throttle every clinician together). `User`
gained `failed_login_attempts`/`locked_until`
(`migrations/versions/19507206caee_login_lockout.py`): 5 failures locks the
account 15 minutes, reset on a successful login. Disabled in tests
(`tests/conftest.py::no_rate_limiting`) — the suite calls these endpoints far
faster than any real client, and rate limiting would make test order/count
affect pass/fail instead of the behavior under test.

**Security headers.** A middleware in `platform/api/main.py` adds
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a
`Content-Security-Policy` (skipped on `/docs`/`/redoc`, which need their own
CDN script/style) to every response.

**HTTPS: header only, no redirect middleware.** Render terminates TLS and
redirects HTTP→HTTPS at its edge (confirmed in `render.yaml`); an app-level
`HTTPSRedirectMiddleware` would be redundant there and would break any
internal/liveness probe that reaches the app over plain HTTP behind that
edge. Instead, `Strict-Transport-Security` is sent whenever
`environment != "development"/"test"` — a real signal to a real browser
without assuming a specific proxy config. If this is ever deployed somewhere
that doesn't already terminate TLS, HSTS is the safety net, not a substitute
for fixing that deployment.

**Imaging path traversal.** `analyze_image`/`describe_image`/
`describe_image_stream`/`detect_image_modality`/`preview_image`
(`platform/api/routers/medical.py`) used to accept any filesystem path the
caller supplied — documented as an intentional "local-first, single-user
tool" trust boundary, but the app runs on a shared Render instance, not a
single user's machine, so any authenticated clinician could read arbitrary
server files. `_resolve_allowed_image_path` now restricts every one of these
to `_ALLOWED_IMAGE_DIRS` (the upload scratch dir, or `real_data/imaging`) —
the only two places a legitimate image ever comes from. `tests/test_medical_router.py`'s
`img_dir` fixture points the module's upload dir at each test's own
`tmp_path` so the existing arbitrary-path test coverage still exercises real
isolated files, just ones that now pass the allow-list.
