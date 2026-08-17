---
id: SPEC-002
title: Tool Runtime
phase: 2
version: 1.2.0
status: Implemented
authors: [jbotero]
created: 2026-08-17
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-001]
adrs: [ADR-002, ADR-010]
features: [F-024, F-025]
diagrams: [D1]
---

# SPEC-002 — Tool Runtime

## 1. Summary

Relocates the MCP tool dispatcher to `src/sephiroth/tools/`, adds a per-call
timeout so a hung tool cannot hang a consultation, adds capability tags so
Phase 3's router has something to query, and closes an authentication gap at
the HTTP layer that predates this migration.

## 2. Motivation

`intelligence/mcp/registry.py::MCPRegistry` already enforces each agent's tool
whitelist at dispatch (`scoped_executor`, added in Phase 0) — that mechanism is
correct and is not redesigned here, only relocated.

Two real gaps remain:

- **No timeout.** `MCPRegistry.execute()` (`intelligence/mcp/registry.py:115-139`)
  calls `client.call_tool(...)` with no bound on how long it may run. Two tools
  perform real I/O — `search_pubmed` (`intelligence/mcp/rag_server.py:46`,
  network) and `describe_medical_image` (`intelligence/mcp/vision_server.py:43`,
  a Gemini call) — and a hang in either blocks the whole consultation with no
  recovery path.
- **No authentication on direct tool endpoints.** `platform/api/routers/medical.py`
  (6 endpoints) and `platform/api/routers/rag.py` (2 endpoints) call
  `registry.execute(...)` directly from FastAPI routes with **zero**
  `Depends(get_current_user)` anywhere in either file — confirmed by grep.
  `platform/api/routers/patients.py:122-124` makes the same kind of call but
  is already behind auth on both of its callers
  (`platform/api/routers/patients.py:170,184`), so it is unaffected. This is
  `DEBT-004` in `docs/project-state.yaml`.

## 3. Goals

- **G-1** Relocate the registry to `src/sephiroth/tools/`, zero behavior
  change to `load`/`llm_tools`/`system_prompt_summary`/`scoped_executor`.
- **G-2** A tool call that exceeds a configured timeout returns an error
  result, never hangs or raises to the caller.
- **G-3** Every tool declares capability tags, queryable by name, for the
  Phase 3 router to consume.
- **G-4** Every endpoint that can trigger tool execution requires
  authentication.

## 4. Non-Goals

- **NG-1** No generic retry wrapper. `search_pubmed` and `describe_medical_image`
  already retry inside their own logic (httpx / `GeminiClient`); a second,
  generic retry layer here would double-retry the same failure for no
  measured benefit.
- **NG-2** No circuit breaker. No incident or requirement justifies one yet;
  recorded as a deferred gap, not built speculatively (`docs/00-project/scope.md`).
- **NG-3** No YAML-driven tool/agent capability loader. Phase 3
  (`docs/02-agents/registry.md`) owns that generality; this phase's tags are a
  hand-authored literal dict.
- **NG-4** No change to `scoped_executor`'s error-result-not-exception
  pattern — that design is already shipped and tested
  (`tests/test_tool_authorization.py`).

## 5. Definitions

- **Tool runtime** — the single dispatcher every tool call passes through,
  whether from an agent or directly from an HTTP route.
- **Capability tag** — a short string naming what a tool does
  (`"medication_interaction"`), consumed by the Phase 3 router, not enforced
  by anything in this phase.

## 6. Contracts

### 6.1 Types

Module: `src/sephiroth/tools/servers.py`

```python
SERVERS: list[FastMCP]
TOOL_CAPABILITIES: dict[str, list[str]]
```

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `SERVERS` | `list[FastMCP]` | yes | — | the 5 existing servers, unchanged set |
| `TOOL_CAPABILITIES` | `dict[str, list[str]]` | yes | — | every key is a real tool name discoverable via `load()` |

### 6.2 Interfaces

Module: `src/sephiroth/tools/runtime.py`

```python
class ToolRuntime:
    def __init__(self, servers: list[FastMCP] | None = None): ...
    async def load(self) -> None: ...
    def llm_tools(self, allowed: list[str] | None = None) -> list[dict]: ...
    def system_prompt_summary(self, allowed: list[str] | None = None) -> str: ...
    def scoped_executor(self, allowed: list[str] | None) -> ToolExecutor: ...
    async def execute(self, tool_name: str, arguments: dict) -> Any: ...
    def tags_for(self, tool_name: str) -> list[str]: ...


def get_tool_runtime() -> ToolRuntime: ...
```

Every method except `execute` (timeout added) and `tags_for` (new) is
byte-identical to `MCPRegistry`.

### 6.3 State machine

`N/A` — no lifecycle beyond the existing `_loaded` idempotency flag.

### 6.4 Errors

| Condition | Result | Maps to |
|---|---|---|
| Unknown tool name | `{"error": "Unknown tool: {name}"}` | unchanged (`FailureCategory.TOOL`) |
| Not authorized for scope | `{"error": "Tool not authorized for this agent: {name}"}` | unchanged (Phase 0) |
| Call exceeds `tool_call_timeout_seconds` | `{"error": "Tool '{name}' timed out after {timeout}s"}` | new; `FailureCategory.TOOL` |

No new exception type. A timeout is caught internally
(`asyncio.TimeoutError`) and converted to the same error-result shape every
other tool failure already uses — consistent with `scoped_executor`'s existing
design (NG-4).

### 6.5 Configuration

| Setting | Type | Default | Note |
|---|---|---|---|
| `tool_call_timeout_seconds` | `float` | `30.0` | new |

## 7. Behaviour

- **B-1** `execute()` MUST NOT let a tool call run longer than
  `tool_call_timeout_seconds`; on timeout it MUST return an error result, never
  raise.
- **B-2** `tags_for(name)` MUST return `[]` for a tool absent from
  `TOOL_CAPABILITIES`, never raise.
- **B-3** Every endpoint in `medical.py` and `rag.py` MUST require
  `Depends(get_current_user)`.
- **B-4** `intelligence.mcp.registry.MCPRegistry` MUST remain the identical
  class object as `sephiroth.tools.runtime.ToolRuntime` (a rename, not a
  reimplementation) — same rule as the Phase 1 shim trap.
- **B-5** `tests/test_mcp.py`, `tests/test_mcp_extra.py`, and
  `tests/test_tool_authorization.py` MUST pass with zero behavioral change
  against the shim.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-002-01 | A tool call exceeding `tool_call_timeout_seconds` returns `{"error": "... timed out ..."}` and does not raise | B-1 | `tests/test_tool_runtime.py` |
| AC-002-02 | `tags_for()` returns the declared tags for each of the 8 tagged tools, and `[]` for an untagged/unknown name | B-2 | `tests/test_tool_runtime.py` |
| AC-002-03 | Every `medical.py`/`rag.py` endpoint returns 401 without a bearer token | B-3 | `tests/test_medical_router.py`, `tests/test_api_patients_rag.py` |
| _(retired)_ | **The fourth and fifth criteria, originally about the `intelligence.mcp.registry` shim's class identity and the three legacy test modules passing unmodified against it, were retired in Phase 4 (DEBT-009)** — the shim they verified was deleted; there is no longer an import surface to check identity against, and the affected modules were retargeted directly onto `sephiroth.tools` instead of staying frozen against a shim. See §10. | B-4, B-5 | — |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit | timeout wrapping, `tags_for` | `tests/test_tool_runtime.py` |
| Shim | class/function identity | _(retired — shim deleted in Phase 4, DEBT-009)_ |
| Integration | auth on direct tool endpoints | `tests/test_medical_router.py`, `tests/test_api_patients_rag.py` |
| Characterization | existing registry behavior, unmodified | the three legacy MCP test modules |

## 10. Migration & Compatibility

Shadowed `intelligence/mcp/registry.py`, which became a re-export shim in this
phase (`MCPRegistry = ToolRuntime`, `get_registry = get_tool_runtime`). The
shim schedule in `docs/00-migration-charter.md` §3 called for deleting it in
Phase 3; Phase 3's approved scope was Agent Runtime + `DEBT-008` and did not
include it, so its deletion was tracked as `DEBT-009` and closed in **Phase
4** instead — one phase later than scheduled, not further, per the charter's
own rule that a shim surviving two phases becomes permanent. All call sites
(`platform/api/routers/{medical,rag,patients}.py`,
`tests/{test_mcp,test_tool_authorization}.py`,
`examples/{tools_example,imaging_example}.py`) were retargeted directly onto
`sephiroth.tools.get_tool_runtime`/`ToolRuntime`.

**Scope correction to that schedule's own prose**: §3 item 4 says shims go in
"`[tool.coverage.report] omit`" — the actual table is `[tool.coverage.run]
omit`; same block, corrected name, fixed in this phase's pull request.

**Only `registry.py` is shimmed**, not the rest of `intelligence/mcp/` — the
five FastMCP servers (`nlp_server.py`, `imaging_server.py`,
`drug_safety_server.py`, `rag_server.py`, `vision_server.py`) remain real
implementation and stay in `coverage.run.source` unchanged.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | A 30s default timeout is a guess, not measured | Recorded as a tunable; revisit once Phase 5 traces make tool latency observable across real runs |
| 2 | Adding auth to `medical.py`/`rag.py` breaks existing unauthenticated tests | Expected and intentional — those tests are updated to register/login first, same pattern as `test_api_agents.py` |
| 3 | Timeout could fire on a legitimately slow `search_pubmed` call under load | Configurable via settings; not addressed by retry (NG-1) since that would mask rather than surface the latency |

## 12. References

- [ADR-002](../08-decisions/ADR-002-mcp-as-tool-layer.md)
- `docs/project-state.yaml` DEBT-004
- [Migration charter](../00-migration-charter.md) §3, §7

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-17 | Initial version; approved as the Phase 2 gate |
| 1.1.0 | 2026-08-17 | Implemented. `sephiroth.tools.servers` importing the five FastMCP server objects back from `intelligence.mcp` created a genuine bidirectional package cycle with the `intelligence/mcp/registry.py` shim (each package needed the other fully initialized). Resolved by making `intelligence/mcp/__init__.py` resolve `MCPRegistry`/`get_registry` lazily via `__getattr__` (PEP 562) instead of importing them eagerly — the shim module itself (`registry.py`) stays a pure two-line re-export; only the package `__init__` gained the lazy-resolution logic. No contract in §6 changed. |
| 1.2.0 | 2026-08-19 | `DEBT-009` closed in Phase 4: `intelligence/mcp/registry.py` deleted (one phase later than the charter's original Phase 3 schedule), all call sites retargeted onto `sephiroth.tools` directly, `intelligence/mcp/__init__.py`'s PEP 562 `__getattr__` removed (no longer needed once nothing requests `MCPRegistry`/`get_registry` from that package). The fourth and fifth acceptance criteria retired — see §8, §10. |
