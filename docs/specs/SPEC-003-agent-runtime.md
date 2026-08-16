---
id: SPEC-003
title: Agent Runtime
phase: 3
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-001, SPEC-002]
adrs: [ADR-001, ADR-004, ADR-010]
features: [F-026, F-027, F-028, F-030, F-031]
diagrams: [D1]
---

# SPEC-003 — Agent Runtime

## 1. Summary

Replaces `intelligence/agents/workflow.py`'s LangGraph-compiled graph with a
purpose-built async executor in `src/sephiroth/runtime/`, and turns the five
clinical agents from hardcoded classes into `AgentCapability` records. Proves
parity by passing the existing test suite unmodified, then removes LangGraph
entirely in the same phase — see `ADR-001`.

## 2. Motivation

`intelligence/agents/workflow.py:107-111` compiles a fixed fan-out whose
destination set must be enumerated at graph-construction time
(`add_conditional_edges(START, ..., list(SPECIALISTS))`). A runtime-decided
agent set — the whole point of a dynamic router in a later phase — cannot be
expressed this way. `intelligence/agents/__init__.py`'s five classes each
hardcoded `name`/`role_prompt`/`allowed_tools` as class attributes, so a
future capability-matching router would have nothing to query; there was no
data representation of "what can this agent do," only a Python class chosen
by name in `platform/api/routers/agents.py:236-250`.

## 3. Goals

- **G-1** Replace the LangGraph executor with one that produces identical
  output against the existing test suite, unmodified.
- **G-2** Turn the five agents into `AgentCapability` data records.
- **G-3** Remove `langgraph` from the dependency tree entirely.
- **G-4** Preserve the frozen SSE/persistence contracts
  (`docs/00-migration-charter.md` §2) exactly.

## 4. Non-Goals

- **NG-1** No dynamic, capability-matching planner. `route_specialists` is
  relocated verbatim, not redesigned — a later phase adds real routing logic.
- **NG-2** No adoption of `sephiroth.contracts.RunState`/`ToolCall`/
  `AgentResult` as the executor's internal state shape. See §10 — this is a
  deliberate deviation from those contracts' original intent, made during
  implementation, not assumed away.
- **NG-3** No change to `citation_guard.py`/`explainability.py` — they are
  called exactly as before; their own relocation is a later phase.
- **NG-4** No parallel "run both and compare" test harness against the old
  LangGraph graph. See `ADR-001`'s Migration section for why this was decided
  unnecessary.

## 5. Definitions

- **Node name** — the underscore-form scheduling identity (`drug_safety`),
  used on the `routing` SSE event.
- **Display name / capability id** — the hyphen-form identity (`drug-safety`),
  used on `agent_completed` and in persistence.

## 6. Contracts

### 6.1 Types

Module: `src/sephiroth/contracts/capability.py` (existing contract, extended)

`AgentCapability` gains one field:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `role_prompt` | `str` | no | `""` | Moved byte-for-byte from the pre-Phase-3 class attributes; substrings `"clinical evidence specialist"` and `"coordinating physician-assistant"` MUST remain present (`FakeLLMClient` trap) |

Module: `src/sephiroth/runtime/registry.py`

```python
RADIOLOGY: AgentCapability
LABORATORY: AgentCapability
DRUG_SAFETY: AgentCapability
EVIDENCE: AgentCapability
COORDINATOR: AgentCapability
SPECIALISTS: dict[str, AgentCapability]  # the 4 the planner selects from
AGENTS: dict[str, AgentCapability]  # all 5, keyed by node name
```

Module: `src/sephiroth/runtime/analyzer.py`

```python
class Signals(TypedDict):
    has_image: bool
    has_lab_results: bool
    has_medications: bool


def analyze(context: dict | None) -> Signals: ...
```

### 6.2 Interfaces

Module: `src/sephiroth/runtime/agent.py`

```python
class Agent:
    def __init__(self, capability: AgentCapability, client: ModelProvider): ...
    @property
    def name(self) -> str: ...  # capability.id
    async def run(self, query: str, context: dict | None = None) -> ChatResult: ...
```

Module: `src/sephiroth/runtime/planner.py`

```python
SPECIALISTS: tuple[str, ...]


def route_specialists(context: dict | None) -> list[str]: ...  # moved verbatim
```

Module: `src/sephiroth/runtime/router.py`

```python
def resolve(node_names: list[str]) -> list[AgentCapability]: ...
```

Module: `src/sephiroth/runtime/executor.py`

```python
async def run_consultation(client, query, patient_id="", context=None) -> dict: ...
async def stream_consultation(client, query, patient_id="", context=None) -> AsyncIterator[dict]: ...
```

`run_consultation`'s return type is a plain `dict`, not `RunState` — see §10.

### 6.3 State machine

`N/A` — no lifecycle beyond "fan out, merge, coordinate." A real agent
lifecycle state machine (`LifecycleState` in contracts, already defined) is a
later phase's addition once there is more than one step per agent to track.

### 6.4 Errors

Unchanged from the pre-existing behaviour: an exception inside one specialist
is not caught here and propagates (matching the old graph's behaviour — error
handling/recovery is a later phase's addition, tracked as a known gap, not
silently assumed solved by this relocation).

### 6.5 Configuration

`N/A` — no new settings.

## 7. Behaviour

- **B-1** `run_consultation`/`stream_consultation` MUST produce output
  indistinguishable from the pre-Phase-3 implementation for every input the
  existing test suite exercises.
- **B-2** The five frozen SSE events (`docs/00-migration-charter.md` §2.1)
  MUST NOT change shape, field names, or casing.
- **B-3** `stream_consultation` MUST yield `agent_completed` progressively, as
  each specialist actually finishes — not all at once after every specialist
  completes. (A plain `asyncio.gather` would regress this; `asyncio.as_completed`
  is used instead.)
- **B-4** Role prompts MUST be byte-identical to their pre-Phase-3 source.
- **B-5** No module under `intelligence/`, `platform/`, or `src/` may import
  `langgraph` after this phase.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-003-01 | `tests/test_workflow.py` passes unmodified | B-1 | that module, run as-is |
| AC-003-02 | `tests/test_sse_contract.py` passes unmodified | B-1, B-2 | that module, run as-is |
| AC-003-03 | `tests/test_api_agents.py` passes unmodified | B-1 | that module, run as-is |
| AC-003-04 | Each of the 5 `AgentCapability` records has a non-empty `role_prompt`, and the two canonical substrings are present on their respective agents | B-4 | `tests/test_prompt_contract.py` |
| AC-003-05 | No module under `intelligence/`, `platform/`, `src/` imports `langgraph` | B-5 | `tests/test_no_langgraph.py` |
| AC-003-06 | `intelligence.agents.workflow.run_consultation is sephiroth.runtime.run_consultation` (shim identity) | — | manual verification + Docker check (this phase did not add a dedicated shim-identity test file, unlike Phases 1–2 — see §10) |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Parity (frozen) | Exact pre-existing assertions against the new executor | `test_workflow.py`, `test_sse_contract.py`, `test_api_agents.py` |
| Contract | Role prompts non-empty, canonical substrings present, mutually distinguishable | `test_prompt_contract.py` (updated to read `AgentCapability.role_prompt` instead of a class attribute) |
| Dependency hygiene | No `langgraph` import anywhere | `test_no_langgraph.py` |

## 10. Migration & Compatibility

Shadows `intelligence/agents/{base,workflow}.py`, which become re-export shims
in this phase (deleted in Phase 4, per the shim schedule). Also resolves
`DEBT-008`: `intelligence/llm/*` (Phase 1 shim, scheduled for Phase 2 deletion
per the original charter, deferred) is deleted in this phase, one phase later
than scheduled — did not slip further, per the charter's rule that a shim
surviving two phases becomes permanent.

**Deviation found during implementation: `RunState` is not adopted yet.**
`sephiroth.contracts.state.RunState` and `results.ToolCall` already existed
(Phase 0) and are strict (`extra="forbid"`). `ToolCall`'s fields
(`id, tool, agent, arguments, result, ok, latency_ms, timestamp`) do not match
the frozen wire shape (`agent, name, arguments, result`) — `tool` vs `name`,
and `id` doesn't exist on the wire. Adopting `RunState` now would mean
constructing strict instances only to immediately flatten them back into the
legacy dict shape for the wire — friction with no benefit, since nothing in
this phase consumes `RunState`'s extra fields (evidence, claims, safety
flags). The executor's internal state is a plain dict shaped like the
pre-Phase-3 `WorkflowState` instead. `RunState` gets adopted in the phase that
actually accumulates evidence/claims/safety data (Phase 4), when its extra
fields stop being dead weight.

**Also decided during implementation:** the original phase plan split this
into "3a" (parity, LangGraph kept alive for a side-by-side comparison test)
and "3b" (LangGraph removed). Both landed in a single phase instead — see
`ADR-001`'s Migration section. Consequently there is no
`tests/test_runtime_parity.py` comparison harness; the three frozen test
modules passing unmodified serve that purpose.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Switching from LangGraph's internal scheduling to `asyncio.as_completed` changes event *timing* | Not asserted by any existing test (none exercises more than one specialist with an order-sensitive assertion); verified manually against a running container |
| 2 | An agent raising an exception during fan-out is unhandled | Matches pre-existing behaviour exactly; real recovery is a tracked future gap (`ADR-007`), not silently introduced or fixed here |
| 3 | `Agent.name` as a property (not a class attribute) breaks any code doing `AgentCls.name` without instantiating | Confirmed via grep: no production call site did this; `tests/test_prompt_contract.py` was the only one and was updated to read `AgentCapability.id` directly |

## 12. References

- [ADR-001](../08-decisions/ADR-001-remove-langgraph.md)
- [ADR-004](../08-decisions/ADR-004-capability-based-routing.md)
- `docs/project-state.yaml` DEBT-008

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved, including the RunState-deferral and LangGraph-removal-timing deviations found during implementation |
