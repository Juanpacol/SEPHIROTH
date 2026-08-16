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
what runs today is metadata inspection plus the vision model.

## Migration (Phases 0–5)

| ID | Feature | Status | Component | Test | Experiment | Docs |
|---|---|---|---|---|---|---|
| F-020 | Formal domain contracts + schema drift gate | ✅ | `sephiroth/contracts/` | `test_contracts_schema.py`, `test_contracts_models.py` | — | SPEC-000 |
| F-021 | Tool authorization enforced at dispatch | ✅ | `mcp/registry.py` | `test_tool_authorization.py` | — | `04-development/setup.md` |
| F-022 | `ModelProvider` interface | 📋 | `sephiroth/models/` | 📋 `test_model_provider_protocol.py` | — | 📋 SPEC-001 |
| F-023 | Config-driven provider selection | 📋 | `sephiroth/models/factory.py` | 📋 | — | 📋 SPEC-001 |
| F-024 | Tool runtime with capability metadata | 📋 | `sephiroth/tools/` | 📋 | — | 📋 SPEC-002 |
| F-025 | Tool timeout / retry / circuit breaker | 📋 | `sephiroth/tools/` | 📋 | — | 📋 SPEC-002 |
| F-026 | Agent registry with declared capabilities | 📋 | `sephiroth/runtime/registry.py` | 📋 | — | 📋 SPEC-003 |
| F-027 | Task analyzer | 📋 | `sephiroth/runtime/analyzer.py` | 📋 | — | 📋 SPEC-003 |
| F-028 | Static planner (parity with `route_specialists`) | 📋 | `sephiroth/runtime/planner.py` | 📋 `test_runtime_parity.py` | — | 📋 SPEC-003 |
| F-029 | Dynamic LLM planner | 📋 | `sephiroth/runtime/planner.py` | 📋 | — | 📋 SPEC-003 |
| F-030 | Capability-based router | 📋 | `sephiroth/runtime/router.py` | 📋 | — | 📋 SPEC-003 |
| F-031 | Executor with deterministic merge | 📋 | `sephiroth/runtime/executor.py` | 📋 `test_runtime_state.py` | — | 📋 SPEC-003 |
| F-032 | Agent lifecycle state machine | 📋 | `sephiroth/runtime/` | 📋 | — | 📋 SPEC-003, D2 |
| F-033 | Recovery engine (retry/fallback/replan/abstain) | 📋 | `sephiroth/runtime/recovery.py` | 📋 | — | 📋 SPEC-003, ADR-007 |
| F-034 | Typed `RunContext` + per-agent views | 📋 | `sephiroth/context/` | 📋 | — | 📋 SPEC-004 |
| F-035 | Reranking, compression, token budgeting | 📋 | `sephiroth/context/` | 📋 | — | 📋 SPEC-004 |
| F-036 | Claim extraction | 📋 | `sephiroth/verification/claims.py` | 📋 | — | 📋 SPEC-004, ADR-006 |
| F-037 | Five-state claim verification | 📋 | `sephiroth/verification/` | 📋 | — | 📋 SPEC-004, ADR-006 |
| F-038 | Conflict detection | 📋 | `sephiroth/verification/` | 📋 | — | 📋 SPEC-004 |
| F-039 | Confidence engine | 📋 | `sephiroth/verification/` | 📋 | — | 📋 SPEC-004 |
| F-040 | Abstention engine | 📋 | `sephiroth/safety/abstention.py` | 📋 | — | 📋 SPEC-004, ADR-008 |
| F-041 | Output safety engine (PHI, injection, HITL) | 📋 | `sephiroth/safety/` | 📋 | — | 📋 SPEC-004 |
| F-042 | Structured execution traces | 📋 | `sephiroth/telemetry/` | 📋 | — | 📋 SPEC-005, ADR-009 |
| F-043 | Span attribute redaction (allow-list) | 🚧 | `contracts/trace.py` | `test_contracts_models.py` | — | 📋 SPEC-005 |

F-043 is 🚧 because the contract and its enforcement exist, but nothing emits
spans yet.

## Removed

| ID | Feature | Status | Note |
|---|---|---|---|
| F-050 | Vestigial `AgentState` dataclass | ⚠️ | Deleted in Phase 0 — zero call sites; superseded by `sephiroth.contracts.RunState` |
| F-051 | `docs/INTEGRATION_GUIDE.md` | ⚠️ | Deleted in Phase 0 — described a structure that never existed |
