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
| F-066 | Appointment reminder + unconfirmed escalation | ⚠️ | `platform/api/workflows/appointment_reminder.py` | `test_appointment_reminder_workflow.py`, `_end_to_end` | — | SPEC-009 §11 risks 3–4 (lead time hard-coded; reschedule loses the reminder) |
| F-067 | Patient appointment confirmation | ✅ | `platform/api/routers/scheduling.py` | `test_api_appointment_confirm.py` | — | SPEC-009 |
| F-068 | Human-in-the-loop approval gate | ⚠️ | `platform/api/routers/approvals.py` | `test_approvals_api.py`, `test_approval_send_path.py` | — | SPEC-009 §11 risk 6 (a draft can be empty) |
| F-069 | Patient follow-up plan (day 3/7/30) | ✅ | `platform/api/workflows/patient_followup.py` | `test_patient_followup_workflow.py`, `test_api_followups.py` | — | SPEC-009 |
| F-070 | Operational memory (namespaced preferences) | ⚠️ | `platform/api/workflows/memory.py` | `test_automation_memory.py`, `test_api_automation_memory.py` | — | SPEC-009 §11 risk 4 (stored and validated, read by nothing) |
| F-071 | Automation observability + ops notifications | ✅ | `platform/api/routers/dashboard.py`, `workflows/ops_notify.py` | `test_dashboard_automation.py`, `test_ops_notify.py`, `test_clinical_notify.py` | — | SPEC-009 |

Five of these are ⚠️ for reasons recorded in SPEC-009 §11 rather than for missing
work: the substrate is live and tested, and each ⚠️ names a specific defect or
deliberate deferral that a later phase closes.

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

## Removed

| ID | Feature | Status | Note |
|---|---|---|---|
| F-050 | Vestigial `AgentState` dataclass | ⚠️ | Deleted in Phase 0 — zero call sites; superseded by `sephiroth.contracts.RunState` |
| F-051 | `docs/INTEGRATION_GUIDE.md` | ⚠️ | Deleted in Phase 0 — described a structure that never existed |
