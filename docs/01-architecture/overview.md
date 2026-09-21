# Architecture overview

> Descriptive, not normative. Contracts live in [`docs/specs/`](../specs/); the
> frozen external interfaces live in [the migration charter](../00-migration-charter.md) §2.
> The target picture is [D1](../09-diagrams/architecture/D1-high-level.md).

Two architectures coexist during the migration. Both are described here, clearly
labelled, because confusing them is the main way this document could mislead.

## Current (what runs today, as of Phase 14 — SPEC-029)

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

**Characteristics.** A consultation always routes to exactly one specialist
(`src/sephiroth/runtime/intent_router.py`) — the multi-agent fan-out and the
coordinator that merged it (`planner.py`, `router.py`, `COORDINATOR`) were
removed in Phase 14 (`SPEC-029`, `ADR-016`) after sitting unreachable in
production since single-specialist routing became the default; `LABORATORY`
was removed alongside it, superseded by `sephiroth.safety.risk`'s
deterministic lab rules. Specialists are `AgentCapability` records
(`src/sephiroth/runtime/registry.py`), not hardcoded classes; LangGraph is gone
(`ADR-001`) in favour of a plain `asyncio`-based executor. Verification is
claim-content verification against retrieved evidence (`SPEC-004`), not just
citation-label auditing.

**What works well and is being kept:** hybrid retrieval with RRF fusion, the MCP
tool layer, the evaluation harness, citation provenance checking, the risk
engine, and the whole clinical application surface.

## Target (what phases 0–5 build)

```
Application
    ↓
Analyzer → Planner → Router → Executor ⇄ Recovery
                                 ↓
              Context Engine · Tool Runtime
                                 ↓
                 Verification → Safety / Abstention
                                 ↓
                        Execution trace
```

**What changes:** routing becomes capability matching; orchestration becomes
plan-driven with replanning; providers sit behind an interface; tool access is
permission-checked at dispatch; verification operates on claim content rather
than citation labels; failures are classified and recovered; every run emits a
replayable trace.

## Layers

| Layer | Responsibility | Phase |
|---|---|---|
| **Agent runtime** | Analyze, plan, route, execute, recover | 3 |
| **Agent management** | Registry, capabilities, lifecycle, policies | 3 |
| **Context engine** | Per-agent context views, lexical reranking, per-patient consultation memory, character budgeting (`src/sephiroth/context/`, SPEC-005) | 4a |
| **Verification & safety** | Claims, evidence, conflicts, confidence, abstention (`src/sephiroth/verification`/`safety`, SPEC-004) | 4b |
| **Tool / MCP runtime** | Registry, capability and permission checks, timeouts | 2 |
| **Model providers** | One interface, many backends | 1 |
| **Observability** | Traces, metrics, structured logging | 5 |

## Stack

FastAPI · SQLAlchemy 2.0 async · PostgreSQL + pgvector · Alembic · Next.js 14 ·
FastMCP · Gemini (Groq fallback) · pytest.

`platform/` is deliberately **not** a Python package — a root `__init__.py`
there would shadow the stdlib `platform` module. It goes on `PYTHONPATH`, so its
subpackages import as top-level. `src/sephiroth/` is importable via editable
install instead, which is what makes it resolve identically under pytest,
uvicorn and Docker.

## Data flow of one consultation, today

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
