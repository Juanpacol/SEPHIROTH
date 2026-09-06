# Feature Registry

The single source of truth for what SEPHIROTH can do. Every row is a capability
a reader could ask "does it do X?" about.

**Status:** 📋 planned · 🚧 in progress · ✅ done · ⚠️ partial or degraded · ❌ blocked

The `Experiment` column stays `—` throughout the architecture migration;
evaluation is out of scope for Phases 0–5 and gets filled in afterwards.

## Shipped

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-001 | Multi-agent clinical consultation (static fan-out) | ✅ | `intelligence/agents/workflow.py` | `test_workflow.py` | — | `ARCHITECTURE.md` |
| F-002 | MCP tool access for agents | ✅ | `intelligence/mcp/` | `test_mcp.py` | — | `04-development/setup.md` |
| F-003 | Citation guard (label provenance audit) | ✅ | `citation_guard.py` | `test_citation_guard.py`, `_adversarial` | — | `06-security/safety.md` |
| F-004 | Rule-based patient risk engine | ✅ | `risk_engine.py` | `test_risk_engine.py` | — | `06-security/safety.md` |
| F-005 | Explainability trace (derived on read) | ✅ | `explainability.py` | `test_sse_contract.py` | — | `00-migration-charter.md` §2.4 |
| F-006 | Hybrid RAG retrieval (keyword + dense, RRF) | ✅ | `data/rag/` | `test_rag_pipeline.py` | — | 📋 `01-architecture/context-engine.md` |
| F-007 | Gemini provider | ✅ | `intelligence/llm/gemini_client.py` | `test_gemini_client.py` | — | ADR-003 |
| F-008 | Groq text-only fallback | ✅ | `fallback_client.py` | `test_fallback_client.py` | — | ADR-003 |
| F-009 | Offline deterministic RAG evaluation (CI gate) | ✅ | `intelligence/evaluation/` | `test_eval_cli.py` | — | `04-development/testing.md` |
| F-010 | JWT auth, single clinician role | ✅ | `platform/auth/` | `test_auth.py` | — | `06-security/threat-model.md` |
| F-011 | Consultation persistence + PDF export | ✅ | `platform/api/` | `test_pdf_export.py` | — | — |
| F-012 | Clinical timeline extraction | ✅ | `timeline_extractor.py` | `test_timeline_extractor.py` | — | — |
| F-013 | Medical imaging analysis | ⚠️ | `imaging_server.py` | — | — | 📋 `02-agents/radiology-agent.md` |
| F-014 | SSE streaming consultation | ✅ | `workflow.py`, `routers/agents.py` | `test_sse_contract.py` | — | `00-migration-charter.md` §2.1 |

F-013 is ⚠️ because MONAI inference is gated behind an unset `monai_model_path`;
what runs today is metadata inspection plus the vision model. The vendored
`intelligence/medical-imaging/` reference tree was deleted in Phase 5
(`DEBT-002`) — it was never imported; `imaging_server.py`'s real-inference
branch already targets the real `monai`/`torch` pip packages (currently
commented out in `requirements.txt`). Activating F-013 means installing
those and validating inference against real weights, not restoring the
vendored tree.

## Migration (Phases 0–5)

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-020 | Formal domain contracts + schema drift gate | ✅ | `sephiroth/contracts/` | `test_contracts_schema.py`, `test_contracts_models.py` | — | SPEC-000 |
| F-021 | Tool authorization enforced at dispatch | ✅ | `mcp/registry.py` | `test_tool_authorization.py` | — | `04-development/setup.md` |
| F-022 | `ModelProvider` interface | ✅ | `sephiroth/models/` | `test_model_provider_protocol.py` | — | SPEC-001 |
| F-023 | Config-driven provider selection (`llm_provider`) | ✅ | `sephiroth/models/factory.py` | `test_llm_factory.py` | — | SPEC-001 |
| F-024 | Tool runtime with capability metadata | ✅ | `sephiroth/tools/` | `test_tool_runtime.py` | — | SPEC-002 |
| F-025 | Tool call timeout | ⚠️ | `sephiroth/tools/runtime.py` | `test_tool_runtime.py` | — | SPEC-002 |
| F-026 | Agent registry with declared capabilities | ✅ | `sephiroth/runtime/registry.py` | `test_agent_registry.py` | — | SPEC-003 |
| F-027 | Task analyzer | ✅ | `sephiroth/runtime/analyzer.py` | `test_agent_registry.py` (via planner) | — | SPEC-003 |
| F-028 | Static planner (parity with `route_specialists`) | ✅ | `sephiroth/runtime/planner.py` | `test_workflow.py` (unmodified parity gate) | — | SPEC-003 |
| F-029 | Dynamic LLM planner | ✅ | `sephiroth/runtime/planner.py` | `test_dynamic_planner.py` | H1 (unmeasured, needs live traffic) | ✅ SPEC-008 |
| F-030 | Capability-based router | ⚠️ | `sephiroth/runtime/router.py` | `test_agent_registry.py` | — | SPEC-003 §4 NG-1 |
| F-031 | Executor (fan-out/merge/coordinate, LangGraph removed) | ✅ | `sephiroth/runtime/executor.py` | `test_runtime_executor.py`, `test_sse_contract.py` | — | SPEC-003 |
| F-032 | Agent lifecycle state machine | ✅ | `src/sephiroth/runtime/executor.py` | ✅ | `tests/test_runtime_executor.py` | ✅ SPEC-007, D2 |
| F-033 | Recovery engine (retry/abstain; fallback/replan NG) | ✅ | `src/sephiroth/runtime/recovery.py` | ✅ | `tests/test_runtime_recovery.py`, `tests/test_runtime_executor.py` | ✅ SPEC-007, ADR-007 |
| F-034 | Typed `RunContext` + per-agent views | ✅ | `sephiroth/context/views.py` | `test_context_views.py` | — | SPEC-005, ADR-011 |
| F-035 | Reranking, memory, token budgeting | ✅ | `sephiroth/context/{rerank,memory,budget}.py` | `test_context_{rerank,memory,budget}.py` | — | SPEC-005, ADR-011 (memory scoped to per-patient recall, not generic session — NG-1) |
| F-036 | Claim extraction | ✅ | `sephiroth/verification/claims.py` | `test_verification_claims.py` | — | SPEC-004, ADR-006 |
| F-037 | Five-state claim verification | ✅ | `sephiroth/verification/verify.py` | `test_verification_verify.py` | — | SPEC-004, ADR-006 |
| F-038 | Conflict detection | ✅ | `sephiroth/verification/verify.py` | `test_verification_verify.py` | — | SPEC-004 |
| F-039 | Confidence engine | ✅ | `sephiroth/verification/confidence.py` | `test_verification_confidence.py` | — | SPEC-004 |
| F-040 | Abstention engine | ✅ | `sephiroth/safety/abstention.py` | `test_safety_abstention.py` | — | SPEC-004, ADR-008 |
| F-041 | Output safety engine (PHI, injection, HITL) | ⚠️ | `sephiroth/safety/output_safety.py` | `test_safety_output_safety.py` | — | SPEC-004 (input prompt-injection heuristic only; PHI/toxicity/jailbreak/HITL deferred, NG-2) |
| F-042 | Structured execution traces | ⚠️ | `sephiroth/telemetry/` | `test_telemetry_build_trace.py` | — | SPEC-006, ADR-009 (spans recorded for 2 of 4 named seams, NG-1) |
| F-043 | Span attribute redaction (allow-list) | ✅ | `contracts/trace.py`, `sephiroth/telemetry/span.py` | `test_contracts_models.py`, `test_telemetry_span.py` | — | SPEC-006 |

F-025 is ⚠️ because only the timeout was built — retry and circuit-breaker
were explicitly deferred (`SPEC-002` NG-1/NG-2): the two I/O-performing tools
already retry inside their own logic (httpx / `GeminiClient`), so a second
generic retry layer would double-retry the same failure with no measured
benefit.

## Automation substrate (Phases 7–14)

Specified retroactively in [SPEC-009](../specs/SPEC-009-automation-substrate.md);
see its §11 for the defects this substrate ships with.

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-060 | Durable tick engine (claim CAS, lease, retry, budget) | ✅ | `platform/api/workflows/engine.py` | `test_workflow_engine_tick.py`, `test_workflow_policy.py` | — | SPEC-009 |
| F-061 | Transactional event outbox | ✅ | `src/sephiroth/workflows/events.py` | `test_workflow_events.py` | — | SPEC-009 |
| F-062 | Step-type registry (literal dict, no name branching) | ✅ | `platform/api/workflows/registry.py` | `test_workflow_engine_tick.py` | — | SPEC-009 |
| F-063 | Notification channel seam | ⚠️ | `platform/api/workflows/channels.py` | `test_workflow_channels.py` | — | SPEC-009 NG-4 (in-app only; no email/SMS/push) |
| F-064 | Alert lifecycle API (review → resolve) | ✅ | `platform/api/routers/alerts.py` | `test_alert_lifecycle_api.py` | — | SPEC-009 |
| F-065 | Alert escalation workflow (window by severity) | ⚠️ | `platform/api/workflows/alert_escalation.py` | `test_alert_escalation_workflow.py`, `_end_to_end` | — | SPEC-009 (single tier; notifies every active clinician, no assignment) |
| F-066 | Appointment reminder + unconfirmed escalation | ✅ | `platform/api/workflows/appointment_reminder.py` | `test_appointment_reminder_workflow.py`, `_end_to_end` | — | SPEC-009; SPEC-009 §11 risks 3–4 closed by SPEC-020 |
| F-067 | Patient appointment confirmation | ✅ | `platform/api/routers/scheduling.py` | `test_api_appointment_confirm.py` | — | SPEC-009 |
| F-068 | Human-in-the-loop approval gate | ✅ | `platform/api/routers/approvals.py` | `test_approvals_api.py`, `test_approval_send_path.py` | — | SPEC-009; the empty-draft defect (§11 risk 6) closed by SPEC-020 |
| F-069 | Patient follow-up plan (day 3/7/30) | ✅ | `platform/api/workflows/patient_followup.py` | `test_patient_followup_workflow.py`, `test_api_followups.py` | — | SPEC-009 |
| F-070 | Operational memory (namespaced preferences) | ✅ | `platform/api/workflows/memory.py` | `test_automation_memory.py`, `test_quiet_hours.py` | — | SPEC-009; read for the first time by SPEC-020 |
| F-071 | Automation observability + ops notifications | ✅ | `platform/api/routers/dashboard.py`, `workflows/ops_notify.py` | `test_dashboard_automation.py`, `test_ops_notify.py`, `test_clinical_notify.py` | — | SPEC-009 |

Three of these were ⚠️ against a defect SPEC-009 §11 recorded rather than against
missing work; SPEC-020 closed those defects and they are ✅ above. `F-063`
(in-app only) and `F-065` (single-tier escalation) remain deliberate deferrals.

## Interface foundations (Phase 15)

Specified in [SPEC-017](../specs/SPEC-017-interface-foundations.md). No new
product capability — these are what the clinical-operating-system phases are
built on, and they land first so no screen is built twice.

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-072 | Portal + focus trap for overlays | ✅ | `platform/frontend/components/ui/portal.tsx`, `lib/hooks/use-focus-trap.ts` | `components/__tests__/sheet.test.tsx` | — | SPEC-017 |
| F-073 | `DataList` — one column set, table and card shapes | ✅ | `platform/frontend/components/ui/data-list.tsx` | `components/__tests__/data-list.test.tsx` | — | SPEC-017 |
| F-074 | Mobile navigation (bottom bar + overflow drawer) | ✅ | `platform/frontend/components/mobile-nav.tsx`, `lib/nav.ts` | `components/__tests__/mobile-nav.test.tsx` | — | SPEC-017 |
| F-075 | Overlay and control primitives (dialog, menu, segmented control, skeleton, toast action) | ✅ | `platform/frontend/components/ui/` | `components/__tests__/sheet.test.tsx` | — | SPEC-017 |
| F-076 | Frontend CI gate (`tsc --noEmit`, eslint at zero warnings) | ✅ | `.github/workflows/ci.yml`, `platform/frontend/.eslintrc.json` | `lib/__tests__/responsive.test.ts` | — | SPEC-017 |

## The clinical task inbox (Phase 16)

Specified in [SPEC-018](../specs/SPEC-018-unified-tasks.md). One inbox for
everything a clinician has to do, replacing five separate surfaces plus a
read-only derived list that nothing could act on.

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-077 | `Task`/`TaskEvent` with an auditable state machine | ✅ | `data/schemas/__init__.py`, `platform/api/services/task_service.py` | `test_task_service_transitions.py` | — | SPEC-018 |
| F-078 | Two-way consistency between a task and its source | ✅ | `platform/api/services/task_adapters.py` | `test_tasks_router.py::TestSourceConsistency` | — | SPEC-018 |
| F-079 | Derivation of unfiled work, with retirement | ✅ | `platform/api/services/task_derivation.py` | `test_task_derivation.py` | — | SPEC-018 |
| F-080 | Task inbox API with filters and offset paging | ✅ | `platform/api/routers/tasks.py` | `test_tasks_router.py` | — | SPEC-018 (the first paginated endpoint in the codebase) |
| F-081 | The inbox UI, with optimistic actions and undo | ✅ | `platform/frontend/app/tasks/`, `lib/hooks/use-task-actions.ts` | `app/tasks/__tests__/page.test.tsx` | — | SPEC-018 |

## Work center and information architecture (Phase 17)

Specified in [SPEC-019](../specs/SPEC-019-work-center.md). The navigation now
names work rather than subsystems; nothing was removed from the product.

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-082 | Flat, work-ordered navigation with redirects for every old URL | ✅ | `platform/frontend/lib/nav.ts`, `lib/routes.ts`, the six redirect stubs | `lib/__tests__/route-restructure.test.ts` | — | SPEC-019 |
| F-083 | `/work` — today first, three counters instead of four | ✅ | `platform/frontend/app/work/`, `components/work/agenda-today-card.tsx` | `components/__tests__/agenda-today-card.test.tsx` | — | SPEC-019 |
| F-084 | Panel-wide `/results` and `/followups` over endpoints that already existed | ✅ | `platform/frontend/app/results/`, `app/followups/` | (covered by the route/nav correspondence test) | — | SPEC-019 |

## Automation correctness (Phase 18)

Specified in [SPEC-020](../specs/SPEC-020-automation-correctness.md). Closes the
defects [SPEC-009](../specs/SPEC-009-automation-substrate.md) §11 recorded.

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-085 | `deferred` step outcome — "not now, ask me again at T" | ✅ | `platform/api/workflows/engine.py`, `registry.py` | `test_workflow_deferral.py` | — | SPEC-020 |
| F-086 | Quiet hours and reminder lead time actually applied | ✅ | `platform/api/workflows/quiet_hours.py`, `appointment_reminder.py` | `test_quiet_hours.py` | — | SPEC-020 |
| F-087 | No-show detection, and a reschedule that keeps its reminder | ✅ | `platform/api/workflows/no_show.py`, `routers/scheduling.py` | `test_no_show_sweep.py` | — | SPEC-020 |
| F-088 | Never an empty draft; a failed automation becomes a task | ✅ | `src/sephiroth/workflows/templates.py`, `workflows/failure_task.py` | `test_approval_draft_endpoint.py`, `test_workflow_deferral.py` | — | SPEC-020 |

Five of the ⚠️ rows in the automation-substrate table above are closed by this
phase; `F-063` (in-app only, no push channel) remains open until SPEC-025.

## Deterministic clinical rules (Phase 19)

Specified in [SPEC-021](../specs/SPEC-021-clinical-rules.md).

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-089 | Stable rule identity, auditable thresholds, no repeat alerts | ✅ | `src/sephiroth/safety/risk.py`, `safety/alerts.py` | `test_clinical_rules.py` | — | SPEC-021 |
| F-090 | Allergy-conflict and duplicate-medication rules; clinical vs administrative | ⚠️ | `src/sephiroth/safety/risk.py` | `test_clinical_rules.py::TestNewRules` | — | SPEC-021 NG-2 (no cross-class inference — no drug-class table exists) |

## Removed

| ID | Feature | Status | Note |
|---|---|---|---|
| F-050 | Vestigial `AgentState` dataclass | ⚠️ | Deleted in Phase 0 — zero call sites; superseded by `sephiroth.contracts.RunState` |
| F-051 | `docs/INTEGRATION_GUIDE.md` | ⚠️ | Deleted in Phase 0 — described a structure that never existed |
