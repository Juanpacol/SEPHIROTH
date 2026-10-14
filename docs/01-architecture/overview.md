# Architecture overview

> Descriptive, not normative. Contracts live in [`docs/specs/`](../specs/); the
> frozen external interfaces live in [the migration charter](../00-migration-charter.md) §2.
> The historical target diagram, [D1](../09-diagrams/architecture/D1-high-level.md),
> is superseded — see "Why there's no 'target' section anymore" below.

## Current (Phase 16 — the only architecture; migration phases 0–16 are all `done`)

```
Next.js  →  FastAPI  →  sephiroth.runtime executor  →  Gemini (+ Groq fallback)
                             │
                     intent_router (keywords → context → LLM classify)
                             │
                    exactly one specialist answers
                     radiology | drug-safety | evidence
                             ↓
                  citation guard → sanitize → claim verification
                             ↓
                     abstention gate → explanation
```

A consultation always routes to exactly one specialist
(`src/sephiroth/runtime/intent_router.py`) — the multi-agent fan-out and the
coordinator that merged it (`planner.py`, `router.py`, `COORDINATOR`) were
removed in Phase 14 (`SPEC-029`, `ADR-016`) after sitting unreachable in
production since single-specialist routing became the default; `LABORATORY`
was removed alongside it, superseded by `sephiroth.safety.risk`'s
deterministic lab rules. Specialists are `AgentCapability` records
(`src/sephiroth/runtime/registry.py`, see [`02-agents/registry.md`](../02-agents/registry.md)),
not hardcoded classes; LangGraph is gone (`ADR-001`) in favour of a plain
`asyncio`-based executor. Verification is claim-content verification against
retrieved evidence (`SPEC-004`), not just citation-label auditing.

**Beyond the consultation path** (phases 7–16, not in the diagram above — it's
request/response, these are durable state machines): a tick-based automation
engine (`platform/api/workflows/`) drives alert escalation, appointment
reminders, and patient follow-up messaging; RAG evidence moved from an
in-memory corpus onto pgvector with no fallback (Phase 15); the dashboard
gained rule-explained alerts with trend/recurrence (Phase 16, `SPEC-031`,
`ADR-019`). A 2026-09-04 security-audit remediation (outside the numbered
phase track) added TOTP MFA, account lockout, API rate limiting, a
least-privilege DB role, and column-level PHI encryption (`ADR-012`/`013`/`014`).

**What works well and is being kept:** hybrid retrieval with RRF fusion, the MCP
tool layer, the evaluation harness, citation provenance checking, the risk
engine, and the whole clinical application surface.

## Why there's no "target" section anymore

This document used to describe two coexisting architectures: "current" (what
ran at Phase 14) and "target" (a capability-matching, plan-driven executor
with replanning, which phases 0–5 were building toward — see the now-superseded
[D1 diagram](../09-diagrams/architecture/D1-high-level.md)). That target
**was built** (phases 0–5), and then Phase 14 **removed** the dynamic
planner/capability-router/replanning layer it added, as unreachable-in-production
dead code (`ADR-016`) — the simpler `intent_router` above replaced it. There is
one architecture now, not two; keeping a "target" section after the target was
built-then-replaced was actively misleading.

## Layers

| Layer | Responsibility | Where |
|---|---|---|
| **Agent runtime** | Route, execute, recover | `src/sephiroth/runtime/` |
| **Context engine** | Per-agent context views, lexical reranking, per-patient consultation memory, character budgeting | `src/sephiroth/context/` (SPEC-005) |
| **Verification & safety** | Claims, evidence, conflicts, confidence, abstention | `src/sephiroth/verification`/`safety` (SPEC-004) |
| **Clinical helpers** | Deterministic, non-LLM: vitals, result classification, templates | `src/sephiroth/clinical/` |
| **Automation engine** | Durable tick-based workflows (alerts, reminders, follow-up) | `platform/api/workflows/` (SPEC-009–016) |
| **Tool / MCP runtime** | Registry, capability and permission checks, timeouts | `src/sephiroth/tools/` (SPEC-002) |
| **Model providers** | One interface, many backends | `src/sephiroth/models/` (SPEC-001) |
| **Observability** | Traces, metrics, structured logging | `src/sephiroth/telemetry/` (SPEC-006) |

## Stack

FastAPI · SQLAlchemy 2.0 async · PostgreSQL + pgvector · Alembic · Next.js 14 ·
FastMCP · Gemini (Groq fallback) · pytest.

`platform/` is deliberately **not** a Python package — a root `__init__.py`
there would shadow the stdlib `platform` module. It goes on `PYTHONPATH`, so its
subpackages import as top-level. `src/sephiroth/` is importable via editable
install instead, which is what makes it resolve identically under pytest,
uvicorn and Docker.

## Data flow of one consultation

1. `POST /api/agents/consult/stream`, authenticated.
2. `intent_router.route_intent(query, context, client)` picks the one
   specialist that answers; a `routing` event is emitted.
3. That specialist runs; it emits `agent_completed` and its answer becomes
   the final answer directly (`_with_disclaimer`) — no coordinator turn.
4. `audit()` checks citations, `sanitize()` strips fabricated ones, claim
   verification and the abstention gate run, `build_explanation()` renders
   the trail; a `final` event is emitted.
5. The consultation is persisted; a `persisted` event carries its id.

The five-event sequence (`routing`, `agent_completed`, `final`, `persisted`,
`error`) is a frozen contract (`docs/00-migration-charter.md` §2) and has
survived every phase since it was introduced.

## Cross-cutting decisions

| Decision | ADR |
|---|---|
| LangGraph removed in favour of a purpose-built executor | [ADR-001](../08-decisions/ADR-001-remove-langgraph.md) |
| MCP as the single tool boundary | [ADR-002](../08-decisions/ADR-002-mcp-as-tool-layer.md) |
| Formal `ModelProvider` interface | [ADR-003](../08-decisions/ADR-003-model-provider-abstraction.md) |
| Capability-based routing | [ADR-004](../08-decisions/ADR-004-capability-based-routing.md) |
| Hybrid retrieval with RRF | [ADR-005](../08-decisions/ADR-005-hybrid-rag.md) |
| Claim-level verification | [ADR-006](../08-decisions/ADR-006-claim-level-verification.md) |
| Explicit classified recovery | [ADR-007](../08-decisions/ADR-007-explicit-recovery.md) |
| Abstention as a first-class output | [ADR-008](../08-decisions/ADR-008-abstention.md) |
| Trace-based observability | [ADR-009](../08-decisions/ADR-009-trace-based-observability.md) |
| Runtime separated from the application | [ADR-010](../08-decisions/ADR-010-runtime-separate-from-application.md) |
| Context engine | [ADR-011](../08-decisions/ADR-011-context-engine.md) |
| Least-privilege DB role; RLS not applicable | [ADR-012](../08-decisions/ADR-012-db-roles-rls.md) |
| API hardening: rate limiting, headers, lockout | [ADR-013](../08-decisions/ADR-013-api-hardening.md) |
| Column-level PHI encryption | [ADR-014](../08-decisions/ADR-014-phi-column-encryption.md) |
| Commit message format | [ADR-015](../08-decisions/ADR-015-commit-message-format.md) |
| Remove coordinator and laboratory | [ADR-016](../08-decisions/ADR-016-remove-coordinator-and-laboratory.md) |
| RAG on pgvector storage | [ADR-017](../08-decisions/ADR-017-rag-pgvector-storage.md) |
| Observation-grounded verification | [ADR-018](../08-decisions/ADR-018-observation-grounded-verification.md) |
| Dashboard explainability visuals | [ADR-019](../08-decisions/ADR-019-dashboard-explainability-visuals.md) |
