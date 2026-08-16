# Architecture overview

> Descriptive, not normative. Contracts live in [`docs/specs/`](../specs/); the
> frozen external interfaces live in [the migration charter](../00-migration-charter.md) §2.
> The target picture is [D1](../09-diagrams/architecture/D1-high-level.md).

Two architectures coexist during the migration. Both are described here, clearly
labelled, because confusing them is the main way this document could mislead.

## Current (what runs today, as of Phase 3)

```
Next.js  →  FastAPI  →  sephiroth.runtime executor  →  Gemini (+ Groq fallback)
                             │
                    static presence-check routing (route_specialists)
                             ├── radiology    → imaging + vision
                             ├── laboratory   → patient context only
                             ├── drug-safety  → interaction table
                             └── evidence     → guidelines + PubMed
                             ↓ asyncio.gather / asyncio.as_completed
                          coordinator
                             ↓
                  citation guard → sanitize → explanation
```

**Characteristics.** Depth is fixed at two. Routing is still a key-presence
check over the request context (`route_specialists`, unchanged in behavior,
relocated to `src/sephiroth/runtime/planner.py`) — dynamic, capability-matching
routing is a later phase. Specialists are `AgentCapability` records
(`src/sephiroth/runtime/registry.py`), not hardcoded classes; LangGraph is gone
(`ADR-001`) in favour of a plain `asyncio`-based executor. Verification still
means auditing citation *labels* against tool output — claim-content
verification is Phase 4.

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
| **Context engine** | Retrieval, ranking, memory, compression, budgeting | 4 |
| **Verification & safety** | Claims, evidence, conflicts, confidence, abstention | 4 |
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
2. `route_specialists(context)` picks branches; a `routing` event is emitted.
3. Selected specialists run concurrently; each emits `agent_completed`.
4. The coordinator joins their outputs and synthesises an answer.
5. `audit()` checks citations, `sanitize()` strips fabricated ones,
   `build_explanation()` renders the trail; a `final` event is emitted.
6. The consultation is persisted; a `persisted` event carries its id.

Steps 2–4 are what Phase 3 replaces; step 5 is what Phase 4 replaces. The event
sequence in steps 2–6 is a frozen contract and survives both.

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
