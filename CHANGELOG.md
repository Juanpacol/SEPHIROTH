# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## SF033

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF032

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF031

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF030

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF029

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF028

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF027

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF026

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF025

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF024

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF023

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF022

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF021

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF020

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF019

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF018

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF017

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF016

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF015

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF014

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF013

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF012

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF011

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF010

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF009

- Auto-update CHANGELOG.md with entries grouped by story [chore]

## SF007

- Auto-generate CHANGELOG.md entries grouped by SF<NNN> story on every push to main [chore]

## SF008

- Route the changelog bot through a PR with a PAT instead of pushing to main directly, since branch protection blocks the default GITHUB_TOKEN [fix]

### Phase E — landing page, brand icon, entry flow (landing/icon/portal/scheduling plan — final phase)

#### Added
- `app/(marketing)/` route group: an English landing page at `/` with its own nav/footer (`components/landing/{landing-nav,landing-footer}.tsx`), escaping `AppShell`'s chrome via `isChromelessRoute()`.
- 4 interactive explanations, zero new dependencies: `ConsultationWalkthrough` (5-stage stepper, autoplay off by default, full `prefers-reduced-motion` support), `ClaimVerifier` (expand-in-place 5-state claim inspector), `CitationGuardToggle` (raw-vs-guarded segmented control, same markup pattern as `ThemeToggle`), `AbstentionGate` (a confidence slider that flips the output card to a decline below threshold).
- Original brand mark: `components/brand/wing-mark.tsx` — a single-wing signature built from stated construction rules (one quadratic-arc spine + feather-rib arcs on a 24×24 grid), stroke-based, `currentColor`. `app/icon.svg` (simplified 2-rib favicon form), `app/apple-icon.tsx`/`app/opengraph-image.tsx` via Next's built-in `next/og` `ImageResponse` (no new dependency, no `public/` directory, no custom font fetch — hermetic in CI).
- Entry flow: `lib/auth-gate.ts::AUTH_GATE_SCRIPT`, an inline `<head>` script (same pre-paint pattern as the existing `THEME_INIT_SCRIPT`) that redirects a logged-in visitor away from `/` before first paint, paired with a `visibility:hidden` CSS rule to prevent any landing-page flash; `components/landing/auth-redirect-gate.tsx` is the client-side fallback for soft navigation back to `/`.
- `app/layout.tsx` gains `metadataBase`/`openGraph`/`twitter` metadata.
- The "S" gradient-square brand mark is replaced by `WingMark` in `sidebar.tsx`, `login/page.tsx`, and `portal/claim/page.tsx`.

#### Verification
- `npm run build`: clean, all 18 routes compile; `/` now shows as `○ Static` (was `redirect()`-only before) — the regression guard that it didn't accidentally become dynamic.
- Production server (`next start`) curled: `/`, `/icon.svg`, `/apple-icon`, `/opengraph-image`, `/login`, `/portal/claim` all return 200; the landing page's actual server-rendered HTML contains the hero copy and the wing-mark SVG, confirming real content renders, not just a shell.
- **UI not verified in a live browser** — no browser automation tool was available in this environment, same limitation as Phase D. The pre-paint redirect mechanism (inline script + CSS rule) cannot be confirmed to eliminate the flash without watching it happen; it follows the exact pattern the existing, working `THEME_INIT_SCRIPT` already uses, which is the basis for confidence here, not a visual check.

### Phase D — frontend: patient portal, schedule UI, role-aware shell (landing/icon/portal/scheduling plan)

#### Added
- `AuthUser`/`UserOut` gain `role`/`patient_id`; `lib/auth.ts::homeFor(role)` is the single mapping from role to post-login destination, used by the login page, the claim page, and the auth guard.
- `components/auth-guard.tsx` — client-side role gate (no `middleware.ts`: the token lives in `localStorage`, invisible to Next middleware). Redirects a patient away from clinician routes and vice versa; also fixes the pre-existing "logged-out users briefly see chrome" flash by rendering `null` until the check completes.
- `lib/routes.ts` — `isChromelessRoute`/`isClinicianRoute`/`isPatientRoute`, the one place route-to-role mapping lives.
- New UI primitives (none existed before): `components/ui/sheet.tsx` (right-side drawer), `components/ui/toast.tsx` (mutation feedback, mounted in `Providers`).
- `components/schedule/{availability-sheet,book-appointment-sheet}.tsx`, `components/results/share-result-sheet.tsx`.
- New pages: `/schedule` (clinician week grid — availability bands via the working-hours sheet, appointment cards positioned by time, cancel-on-click), `/portal`, `/portal/appointments`, `/portal/results`, `/portal/results/[id]`, `/portal/claim` (public claim-code redemption).
- `lib/api.ts`: full typed methods for scheduling (`availability`, `exceptions`, `slots`, `appointments`, `agendaToday`), results (`shareableEvents`, `createShare`, `uploadAttachment`, `listShares`, `getShare`, `downloadAttachment`), portal (`portalMe`, `portalTimeline`, `portalLabs`, `claimInvite`), and `createInvite`. Added the missing `del()` helper and an `ApiError` class carrying HTTP status (so a 403 renders as "not available for your account" instead of a generic failure).
- `date-fns` — the only new frontend dependency, used for week navigation in `/schedule`.
- Dashboard: a "Today's agenda" card (new `GET /api/scheduling/agenda/today` query) below the KPI row.
- Patient detail page: an "Invite to portal" button (copies the claim code to the clipboard) and a "Share a result" action opening `ShareResultSheet`.

#### Changed
- `components/app-shell.tsx` generalizes its `pathname === "/login"` bail into `isChromelessRoute`, and wraps chrome in `AuthGuard`.
- `components/sidebar.tsx` renders `CLINICIAN_NAV` or `PATIENT_NAV` depending on `useUser()?.role`; `components/topbar.tsx` wires the previously-dead `CalendarClock` button to `/schedule` (clinician only) and routes the avatar link to `/portal` for a patient.
- `app/login/page.tsx`: post-login routing uses `homeFor(role)` instead of a hardcoded `/dashboard`; adds a "Have a claim code?" link to `/portal/claim`.
- Attachment downloads use `getBlob` + `URL.createObjectURL` (same pattern as the existing PDF export), not a plain `<a href>` — the token lives in localStorage, so a direct browser navigation to an authenticated download route would 401.

#### Verification
- `npm run build`: clean, all 17 routes compile and type-check (including the two dynamic routes, `/patients/[id]` and `/portal/results/[id]`).
- **UI not verified in a live browser** — no browser automation tool was available in this environment. Verified instead via a clean production build (full TypeScript check across every page) and a running dev server + backend, curling every new route for a non-error HTTP status. This is a real limitation of this verification pass, not a claim of full UI correctness — the golden-path click-through (register → book → invite → claim → share → download) has not been visually confirmed.

### Phase C — scheduling + exam-results backend (landing/icon/portal/scheduling plan)

#### Added
- 5 new tables: `AvailabilityRule` (recurring weekly working hours, wall-clock + IANA timezone), `AvailabilityException` (one-off block/open), `Appointment` (clinician+patient, half-open-interval conflict rules, soft-cancel only), `ResultShare` (references an existing `TimelineEvent` — no new "lab result" entity), `ResultAttachment` (Postgres `LargeBinary`, `deferred=True`, sha256, 10MB/3-file caps).
- `platform/api/scheduling.py::expand_slots` — a pure function computing every open, bookable slot from rules/exceptions/existing bookings; never materialized. Handles DST via `zoneinfo`, with a documented limitation (doesn't collapse/expand slot count across a spring-forward/fall-back transition — always one slot per configured step).
- `platform/core/storage.py` — a `BlobStore` Protocol behind `ResultAttachment.content`, so a later move to S3/object storage is one class, not a router rewrite.
- New routers `scheduling.py` (`/availability`, `/exceptions`, `/slots`, `/appointments`, `/agenda/today`) and `results.py` (`/shareable/{patient_id}`, `/shares`, `/shares/{id}/attachments`, `/attachments/{id}/download`) — both role-scoped per-route (no blanket router guard), unlike Phase A/B's clinician-only routers.
- New authenticated `GET /api/scheduling/agenda/today` + regression lock proving `/api/dashboard/stats`'s shape is untouched (deliberately not folding per-clinician agenda data into that global route).
- Migration `08a4a2ef03ab` on top of `3b2f5725233c` — autogenerate got everything right this cycle (check constraints, cascade delete, server defaults, unique constraints) with zero hand-fixes needed.
- ~120 new tests across `test_scheduling_slots.py` (pure-function DST/chunking/exception cases), `test_scheduling_models.py`, `test_api_scheduling_availability.py`, `test_api_scheduling_appointments.py`, `test_api_scheduling_edge_cases.py`, `test_api_result_shares.py`, `test_result_attachments.py`, `test_api_agenda_today.py`.

#### Fixed — a real conflict-precedence bug found by the appointment test suite
- `POST /api/scheduling/appointments` returned 422 ("outside working hours") instead of 409 ("conflict") when booking the exact same already-booked slot: the working-hours check was computing `expand_slots` with existing appointments included, which subtracts booked slots from the candidate set — making a genuinely-booked slot look like it was never in working hours at all, hiding the real conflict. Fixed by computing working-hours membership against rules/exceptions only, independent of existing bookings; the explicit conflict queries are what now correctly produce the 409.

#### Non-goals (stated up front, not discovered mid-build)
- A true DB-level double-booking exclusion constraint (Postgres `EXCLUDE USING gist`) — no SQLite equivalent, would break the test fixture; mitigated with a transactional check instead.
- Recurring appointment series, waitlists, any notification channel (email/SMS/push) — `viewed_at` is the only "read" signal.
- Object storage (S3) for attachments — the `storage.py` seam makes this a later swap, not built now.

#### Verification
- `pytest --cov`: 656 passed, ~90% coverage.
- `intelligence.evaluation.run --mode ci`: PASS, unchanged.
- `docs_check.py` / `export_contracts.py --check`: OK, no shape change.
- `bandit`: 0 High severity/confidence findings.
- Migration applied, downgraded, and re-applied against real local Postgres; drift guard ran (not skipped) and passed.
- Docker build + smoke test + a manual booking/conflict/sharing flow verified against a real container next.

### Phase B — roles + patient portal auth (landing/icon/portal/scheduling plan)

#### Added
- `User.role` (default `"clinician"`, `server_default` backfills every existing row) and `User.patient_id` (nullable, unique FK → `patients.id`) — a `CheckConstraint` makes a patient role with no bound chart unrepresentable at the DB level.
- New table `PatientInvite` — a clinician-issued, one-time, 72h-expiring claim code (bcrypt-hashed secret) letting a known `Patient` create a portal login. **No patient self-registration path exists**; identity proofing is a human, in-clinic step this system doesn't attempt to verify from form fields.
- `platform/auth/deps.py`: `require_clinician`, `require_patient`, `current_patient_record` (derives the patient from the token, never a path/query param), `require_clinician_for_registration` (gates `POST /api/auth/register` behind a clinician token once `settings.allow_bootstrap_registration` — default on — is turned off).
- `POST /api/patients/{id}/invites` (clinician-only) issues a claim code; `POST /api/auth/portal/claim` (public) redeems it. Every claim failure mode (unknown id, already redeemed, expired, wrong secret) returns the identical generic 400 — distinguishing them would make the endpoint an oracle for enumerating invite ids.
- New router `platform/api/routers/portal.py`: `GET /api/portal/{me,timeline,labs}` — the patient's own chart, trimmed (no rule-derived `risk_level`/`risk_flags`; AI-generated timeline events filtered out unless explicitly shared).
- `UserOut` gains `role`, `patient_id`.
- New migration `3b2f5725233c` on top of `233988357f83`. Hand-fixed: autogenerate named `users.patient_id`'s FK `None` in both directions (no `naming_convention` configured) — `op.drop_constraint(None, ...)` isn't droppable by name, so `downgrade()` would have failed; named it explicitly.
- Tests: `tests/test_portal_isolation.py` (patient A can't read B, patient can't reach any clinician route, clinician keeps full access, plus a route-shape meta-test asserting every clinician route carries `require_clinician` and no portal route takes a `patient_id`), `tests/test_patient_invite.py` (happy path, replay, expiry, wrong secret, unique-FK double-claim, extra-field rejection), `tests/test_portal_endpoints.py` (portal reads, the bootstrap-flag-off path, a 404 when a portal login's bound chart has been deleted).

#### Fixed — two pre-existing Postgres-only bugs, found during Docker/manual verification, invisible to the SQLite test suite (it never enables `PRAGMA foreign_keys`, and its driver tolerates a lazy-load SQLite's async dialect doesn't reject)
- `POST /api/patients` 500'd on every real deployment: `patient.timeline = []` after `commit()` (which expires attributes) triggered an implicit lazy-load outside an awaited context — asyncpg's async dialect raises `MissingGreenlet`, SQLite's driver silently tolerated it. No test exercised the successful-creation path before this phase. Fixed with `session.refresh(patient, attribute_names=["timeline"])`, an explicit in-band load.
- `POST /api/auth/portal/claim` 500'd on every real deployment: setting `invite.redeemed_user_id = user.id` before flushing the new `user` row works on SQLite (no FK enforcement) but Postgres rejects the UPDATE — the column is a plain FK, not a relationship, so nothing tells the unit of work to insert the user first. Fixed with an explicit `session.flush()` before setting the redeemed fields.
- Both fixed and reverified with the actual invite→claim→portal-read→403-on-clinician-route flow run against a real local Postgres (not just the SQLite suite) before rebuilding the Docker image.

#### Changed
- `platform/api/main.py`: the clinician-only routers now carry `dependencies=[Depends(require_clinician)]` (was the Phase A placeholder `get_current_user`) — swapping in the real role check was the one-line change Phase A's commit message promised.
- `tests/test_auth.py`: `test_update_profile`'s exact-set assertion extended for the two new additive `UserOut` fields; added `test_registration_defaults_to_clinician_role` and `test_register_rejects_role_and_patient_id_fields`.
- `tests/test_api_patients_rag.py`: added `test_create_patient_returns_full_record_with_empty_timeline` — the missing successful-creation test that should have caught the first bug above.

#### Verification
- `pytest --cov`: 579 passed, 93% coverage.
- `intelligence.evaluation.run --mode ci`: PASS, unchanged.
- `docs_check.py` / `export_contracts.py --check`: OK, no contract shape change (SQLAlchemy models, not `sephiroth.contracts`).
- `bandit`: 0 High severity/confidence findings.
- Migration applied, downgraded, and re-applied against a real local Postgres; `tests/test_alembic_migration.py`'s drift guard ran (not skipped) and passed.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase A — close unauthenticated PHI exposure (patient portal/scheduling plan)

#### Security
- **`GET/POST /api/patients`, `GET /api/patients/{id}`, `GET /api/patients/{id}/timeline`, and `GET /api/dashboard/stats` had no authentication at all** — any unauthenticated caller could list every patient's PHI or read aggregate risk counts. Fixed via a router-level `dependencies=[Depends(get_current_user)]` on the `agents`, `patients`, `medical`, `rag`, and `dashboard` router includes in `platform/api/main.py`, so a future route added to any of these files is protected the moment it exists rather than requiring a per-handler audit.
- `get_current_user` is a deliberate stand-in for a `require_clinician` dependency landing in a later phase (roles/patient-portal auth) — swapping it in is a one-line change once that exists.

#### Added
- 6 regression-lock tests in `tests/test_api_patients_rag.py` (`test_unauthenticated_cannot_*`), written to fail against the pre-fix code and confirmed they did.

#### Changed
- `tests/test_api_patients_rag.py` builds its own `FastAPI()` app rather than importing `api.main`'s — mirrored the same `dependencies=` there, and updated every existing test that hit `/api/patients*`/`/api/dashboard/stats` unauthenticated to register a clinician and pass a Bearer header.
- `scripts/smoke_test.sh`: its dashboard check now sends the Bearer token it already has from registering, instead of an unauthenticated request.

#### Verification
- `pytest --cov`: 537 passed, 1 skipped, 93.23% coverage.
- `intelligence.evaluation.run --mode ci`: PASS, unchanged.
- `docs_check.py` / `export_contracts.py --check`: OK, no contract shape change.
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 5 — DEBT-001/002/003 cleanup (final part of the 5-part plan)

#### Removed
- **`DEBT-001`**: `intelligence/nlp/{ner,pipeline,preprocessing}/` (11 files, ~1581 lines) — vendored MedCAT, zero call sites confirmed by grep before removal. `intelligence/nlp/__init__.py` (the `ClinicalEntityExtractor`/`ClinicalTextProcessor` stub classes) and `timeline_extractor.py` are untouched — neither imported the deleted tree either.
- **`DEBT-002`**: `intelligence/medical-imaging/` (157 files) — vendored MONAI, also zero call sites. `intelligence/mcp/imaging_server.py`'s real-inference branch already imports the real `monai`/`torch` pip packages directly (both commented out in `requirements.txt`, gated behind `settings.monai_model_path`); it never referenced this vendored tree. Activating F-013 means installing those packages and validating inference, not restoring vendored code.
- Now-orphaned `ruff`/`bandit` `exclude`/`exclude_dirs` entries for both deleted trees.

#### Changed
- **`DEBT-003`**: `data/schemas/__init__.py::GuidelineDocument`'s docstring rewritten to state plainly that no route reads or writes this table today — resolved by documenting it as intentional cold storage, not by building an ingestion endpoint (no validated product need).
- `docs/project-state.yaml`: all 3 `DEBT` entries marked `resolved`; `intelligence/nlp/ner`'s standalone `deprecated` component entry removed (the directory no longer exists); phase 5 marked `done`; version bumped to `1.0.0` — this closes the 5-part plan.

#### Verification
- `pytest --cov`: 532 passed, 1 skipped, 93.23% coverage — unchanged from Part 4 (neither deleted tree had any tests to lose).
- `intelligence.evaluation.run --mode ci`: PASS, all 6 metrics unchanged.
- `docs_check.py`: OK (no deleted path still referenced in `project-state.yaml`). `export_contracts.py --check`: OK, 24 schemas, no shape change.
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 4 — Dynamic capability-matching planner

#### Added
- **`src/sephiroth/runtime/planner.py::route_specialists_dynamic(context, client)`** (`docs/specs/SPEC-008-dynamic-planner.md`, closes `SPEC-003` NG-1): asks the model which of the four specialists are relevant via one `generate_json` call constrained to the four known node names, instead of the static key-presence heuristic. Degrades to `route_specialists` (unchanged) on any exception, non-dict payload, or empty/all-unknown `agents` list.
- New setting `enable_dynamic_planner` (default `False`, `platform/core/config.py`) gates which planner `_route` (new helper in `executor.py`) uses. Default off keeps the offline eval (`--mode ci`, no live model) on the static path.
- `tests/test_dynamic_planner.py`: the same 4 static-parity cases (image/labs/medications/none) via a scripted `FakeLLMClient`, plus degradation cases (exception, non-dict, malformed, unknown-name filtering), plus 2 integration tests wiring the flag through `run_consultation`/`stream_consultation`.

#### Changed
- `src/sephiroth/runtime/executor.py` promotes the previously duplicated `node_names = route_specialists(context)` line at both entry points into a shared `_route(context, client)` helper.

#### Known deviations (`SPEC-008` §4)
- **`H1` (unnecessary invocation rate) is not measured** (NG-3) — needs live traffic with the flag on; this spec makes the metric answerable, not answered.
- **No prompt tuning** — the routing prompt is untuned; validating real model behavior needs a live `GEMINI_API_KEY` run this environment cannot provide.

#### Verification — this is the highest-risk part of the 5-part plan (touches the frozen `routing` SSE event)
- `pytest --cov`: 532 passed, 1 skipped, 93.19% coverage; `planner.py` 100%.
- **Frozen contract suite passes unmodified with the flag at its default (off)**: `test_workflow.py`, `test_sse_contract.py`, `test_api_agents.py` — the evidence this change is additive.
- `intelligence.evaluation.run --mode ci`: PASS, all 6 metrics unchanged (flag off).
- `docs_check.py`: OK, all AC-008-0{1..4} anchors resolved. `export_contracts.py --check`: OK, 24 schemas, no shape change.
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 3 — Relocate `risk_engine`/`citation_guard`/`explainability`

#### Added
- **`src/sephiroth/safety/risk.py`**, **`src/sephiroth/verification/citation_guard.py`**, **`src/sephiroth/telemetry/explain.py`** — byte-for-byte relocations of `intelligence/agents/{risk_engine,citation_guard,explainability}.py`. No logic changed.
- `intelligence/agents/{risk_engine,citation_guard,explainability}.py` are now pure re-export shims (`docs/00-migration-charter.md` rule 1), deleted in Phase 6 per rule 3.
- `tests/test_shim_identity_relocation.py` — identity assertions (`shim.x is new.x`) for all 3, per charter rule 2.
- `[tool.coverage.report] omit` added for the 3 shim paths (charter rule 4).
- `src/sephiroth/runtime/executor.py` promotes `citation_guard`/`explainability` from deferred, function-local imports to normal module-level imports — the cross-package ordering hazard that justified deferring them (`intelligence.agents` importing at module scope) no longer applies once both live under `src/sephiroth/`.

#### Changed
- `platform/api/routers/{patients,dashboard,agents}.py` and `intelligence/evaluation/metrics.py` import from the new `src/sephiroth/` paths directly instead of through the shim.
- `tests/test_risk_engine.py`, `tests/test_citation_guard.py`, `tests/test_citation_guard_adversarial.py` retargeted to the new import paths (same assertions).

#### Verification
- `pytest --cov`: 522 passed, 1 skipped, 93.17% coverage; all 3 relocated modules at 98-100%; shims correctly absent from the coverage report (`omit`).
- `intelligence.evaluation.run --mode ci`: PASS, all 6 metrics unchanged.
- `docs_check.py`: OK. `export_contracts.py --check`: OK, 24 schemas, no shape change.
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 2 — Recovery engine + lifecycle state machine

#### Added
- **`src/sephiroth/runtime/recovery.py`** (`docs/specs/SPEC-007-recovery.md`, executes `ADR-007`): `classify(exc, component, step_id, attempt) -> Failure` maps an exception to a `FailureCategory` (`MODEL` for `LLMUnavailableError`, `AGENT` for anything else); `decide_recovery(failure, attempt, max_attempts) -> RecoveryActionType` returns `RETRY` for a transient category (`MODEL`/`TOOL`) with attempts remaining, `ABSTAIN` otherwise.
- `src/sephiroth/runtime/executor.py::_run_specialist` now wraps each specialist's turn in a bounded retry loop (`MAX_AGENT_ATTEMPTS=2`, matching `PlanStep.max_attempts`'s default). An exhausted specialist no longer raises past itself — it returns an `AgentResult` with empty content, and the consultation completes using the other specialists' output plus the coordinator's synthesis.
- `RunState.lifecycle`/`.failures`/`.retries`/`.recovery_actions` (typed contracts since Phase 0, never populated) are filled for the first time: each capability moves through `SELECTED → EXECUTING → (COMPLETED | RECOVERING → COMPLETED | FAILED)`.
- Tests: `tests/test_runtime_recovery.py` (unit table for `classify`/`decide_recovery`, no LLM); `tests/test_runtime_executor.py::test_transient_model_failure_retries_then_succeeds` (new); `test_one_specialist_raising_does_not_abort_the_others` rewritten to assert the new behaviour instead of clean propagation.

#### Changed
- **Behaviour change, deliberate**: before this cycle, an unhandled exception from any specialist aborted the entire consultation — this was documented in the old test's own docstring as a tracked gap, not a guarantee. It's now closed: a non-transient (`AGENT`-category) failure abstains immediately; a transient (`MODEL`-category) failure gets one retry before abstaining.

#### Known deviations (`SPEC-007` §4)
- **`FALLBACK` and `REPLAN` are not implemented** (NG-1, NG-2) — one agent per capability today (no alternative to fall back to); no dynamic planner yet to replan against (`SPEC-008`, still pending).
- **The coordinator's own call is not covered by this recovery loop** (NG-3) — it's the final synthesis step with nothing to substitute for it; a coordinator failure still propagates unchanged, exactly as before this spec.
- **`TOOL` category has no real trigger yet** (NG-4) — included in `decide_recovery`'s transient set for symmetry with `MODEL`, but `ToolRuntime.execute` already degrades a timeout to an error result rather than raising, so this branch is currently unreachable dead code.

#### Verification
- `pytest --cov`: 519 passed, 1 skipped, 93.17% total coverage; `recovery.py` and `executor.py` both 100%.
- `intelligence.evaluation.run --mode ci`: PASS, all 6 metrics unchanged from Part 1.
- `docs_check.py`: OK, all AC-007-0{1..5} anchors resolved.
- `export_contracts.py --check`: OK, 24 schemas — no contract shape change (reuses existing `Failure`/`RecoveryAction`/enums).
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 1 — Telemetry (trace-based observability)

#### Added
- **`src/sephiroth/telemetry/`** (`docs/specs/SPEC-006-telemetry.md`, executes `ADR-009`): `build_trace(state) -> ExecutionTrace` projects a fully-populated `RunState` into the persisted, replayable trace contract that's existed since Phase 0 but had nothing emitting into it until now. `traced_span(state, kind, name, **attrs)` records real spans for two of `ADR-009`'s four named seams — `Executor.step` (one per specialist/coordinator turn) and `Verifier.check` (the claim-verification/abstention pass) — timed with `time.monotonic()`, redacted via the pre-existing attribute allow-list (dropped, not raised, on a disallowed key — instrumentation must never break a run).
- `RunState` gains one additive field, `spans: list[Span] = []`.
- New setting `enable_tracing` (default `True`, `platform/core/config.py`) — when `False`, `traced_span` is a pure no-op; a run must produce an identical result with tracing on vs. off apart from the trace itself (ADR-009's H6 requirement, now covered by a real test).
- Five new nullable `Consultation` columns: `trace` (JSON) plus the four indexed scalars `ADR-009` names — `trace_id`, `risk_level`, `abstained`, `supported_claim_ratio`. New migration `233988357f83`.
- `ConsultResponse`, the SSE `final` event, and `/history` all gain `trace` as an additive, optional field.
- Tests: `tests/test_telemetry_{span,build_trace}.py`, plus a new H6 parity test in `tests/test_runtime_executor.py`.

#### Known deviations (`SPEC-006` §4, §10)
- **`ModelProvider.chat` and `ToolRuntime.execute` are not independently instrumented this cycle** (NG-1) — `ToolRuntime` is a shared singleton with no per-request state, and threading one through would change `ToolExecutor`'s `Callable` signature that `FakeLLMClient` and every `scoped_executor()` call site already depend on; `Agent.run()` makes exactly one `chat()` call per turn today, so the `Executor.step` span already bounds it as tightly as a nested span would.
- **Token/cost accounting is a placeholder** (NG-2) — `ChatResult`/`AgentResult` don't carry usage metadata from the model clients yet.
- **No pluggable Tracer/OTel backend** (NG-3) — premature with a single consumer (the new Postgres columns); `opentelemetry-api` is already present as a transitive dependency but not wired to anything.
- **Friction found during implementation**: `VerificationReport.supported_claim_ratio` is a Pydantic `@property`, not a `computed_field` — it doesn't appear in `model_dump()`'s output. `_persist` recomputes it directly from the already-serialized `verification_report`'s claim statuses instead of reading a field that would have silently always been `None`.

Older entries (DEBT-010 through the 0.1.0 initial release) moved to
[`docs/CHANGELOG-archive.md`](docs/CHANGELOG-archive.md) to keep this file
compact — same content, nothing lost.
