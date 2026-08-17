---
id: SPEC-007
title: Recovery Engine + Agent Lifecycle
phase: 5
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-003]
adrs: [ADR-007]
features: [F-032, F-033]
diagrams: [D2]
---

# SPEC-007 — Recovery Engine + Agent Lifecycle

## 1. Summary

Executes `ADR-007`: classifies a specialist's failure and picks a bounded
recovery action (`RETRY` or `ABSTAIN`), instead of letting an unhandled
exception propagate and abort the whole consultation — a documented,
tracked gap since Phase 3, never closed until now. `RunState.lifecycle`
(existing since Phase 0, never populated) is filled as each specialist
moves through `SELECTED → EXECUTING → (COMPLETED | RECOVERING → COMPLETED
| FAILED)`.

## 2. Motivation

Before this spec, `tests/test_runtime_executor.py::test_one_specialist_raising_does_not_abort_the_others`
documented, by name, that "no recovery yet" was a tracked future gap: a
`RuntimeError` from any specialist aborted the entire consultation, even
though 3 other specialists may have already succeeded. `ADR-007`'s
contracts (`FailureCategory`, `RecoveryActionType`, `LifecycleState`,
`Failure`, `RecoveryAction`) have existed since Phase 0, fully typed, sitting
unused.

## 3. Goals

- **G-1** `classify(exc, component) -> Failure` maps an exception to a
  `FailureCategory` — `MODEL` for `LLMUnavailableError` (rate limit, quota,
  transient outage), `AGENT` for anything else raised during a specialist's
  turn.
- **G-2** `decide_recovery(failure, attempt, max_attempts) -> RecoveryActionType`
  — `RETRY` for a transient category (`MODEL`/`TOOL`) with attempts
  remaining, `ABSTAIN` otherwise.
- **G-3** `_run_specialist` retries a transient failure up to
  `MAX_AGENT_ATTEMPTS` (2, matching `PlanStep.max_attempts`'s default) and
  never raises past itself — an exhausted specialist contributes an empty
  section rather than aborting the run.
- **G-4** `RunState.lifecycle`/`.failures`/`.retries`/`.recovery_actions`
  are populated for every specialist, every run.

## 4. Non-Goals

- **NG-1** `REPLAN`. There is no dynamic planner yet (`SPEC-003` NG-1) to
  revise a plan against — replanning over a static, four-branch route has
  nothing to reconsider. Revisit once `SPEC-008` (dynamic planner) exists.
- **NG-2** `FALLBACK`. One agent per capability today — there is no
  alternative agent to fall back to for a failed specialist.
- **NG-3** Recovery for the coordinator's own call. The coordinator is the
  final synthesis step with nothing to substitute for it; a coordinator
  failure still propagates unchanged, exactly as before this spec. Recovery
  is scoped to the fan-out (specialist) stage only, per the approved plan.
- **NG-4** A `TOOL`-category failure path with a real trigger. `TOOL` is
  named in `decide_recovery`'s transient set (symmetric with `MODEL`, and
  cheap to include), but nothing in this cycle's call sites raises a
  tool-specific exception distinguishable from a generic `AGENT` failure —
  `ToolRuntime.execute` already degrades timeouts to an error *result*
  (SPEC-002), not a raised exception, so this branch is currently dead code
  reachable only if a future change makes tool execution raise. Not
  removed, since the categorization is free and correct once that happens.

## 5. Definitions

- **Transient failure** — a `FailureCategory` (`MODEL`, `TOOL`) whose cause
  is plausibly resolved by trying again unchanged.
- **Exhausted** — `attempt >= max_attempts`; no further `RETRY` is offered.

## 6. Contracts

### 6.1 Types

No contract types change shape — this spec is the first real consumer of
`Failure`, `RecoveryAction`, `FailureCategory`, `RecoveryActionType`,
`LifecycleState`, all defined since Phase 0.

### 6.2 Interfaces

```python
# src/sephiroth/runtime/recovery.py
def classify(exc: Exception, component: str, step_id: str | None = None, attempt: int = 1) -> Failure: ...
def decide_recovery(failure: Failure, attempt: int, max_attempts: int) -> RecoveryActionType: ...
```

### 6.3 State machine

Per specialist, per run: `SELECTED` (set when capabilities are resolved) →
`EXECUTING` (set when `_run_specialist` starts) → `COMPLETED` (success) |
`RECOVERING` (a `RETRY` was chosen; loops back to `EXECUTING` on the next
attempt) | `FAILED` (an `ABSTAIN` recovery action was recorded — retries
exhausted, or the failure category was never transient). Matches `D2`
(`docs/09-diagrams/architecture/D2-agent-lifecycle.md`).

### 6.4 Errors

`_run_specialist` never raises past itself once `MAX_AGENT_ATTEMPTS` is
reached — the caller (`run_consultation`/`stream_consultation`) always
gets back a `(capability, AgentResult, list[ToolCall])` tuple, with
`AgentResult.content == ""` and `tool_calls == []` when the specialist
never produced a usable result.

### 6.5 Configuration

| Setting | Module | Default | Status |
|---|---|---|---|
| `MAX_AGENT_ATTEMPTS` | `src/sephiroth/runtime/executor.py` (module constant) | `2` | matches `PlanStep.max_attempts`'s default |

## 7. Behaviour

- **B-1** A `MODEL`-category failure is retried once (2 attempts total)
  before the specialist abstains.
- **B-2** An `AGENT`-category failure abstains on the first attempt — it is
  never classified as transient.
- **B-3** A failed specialist's entry still appears in
  `state.agent_results`/`agent_outputs` (with empty content) — it was
  selected and attempted, even though it contributed nothing; downstream
  code (the coordinator's section-joining, `agents_involved`) is unaffected
  because an empty section joins to nothing visible.
- **B-4** The coordinator's own call is not wrapped in this recovery loop —
  a coordinator failure still propagates exactly as before this spec (NG-3).
- **B-5** Every `RETRY` records a `RecoveryAction` with `succeeded=None`
  (outcome not yet known); every terminal `ABSTAIN` records one with
  `succeeded=False`.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-007-01 | `classify` maps `LLMUnavailableError` to `MODEL`, any other exception to `AGENT` | G-1 | `tests/test_runtime_recovery.py` |
| AC-007-02 | `decide_recovery` returns `RETRY` while attempts remain for a transient category, `ABSTAIN` otherwise (including immediately for non-transient categories) | G-2 | `tests/test_runtime_recovery.py` |
| AC-007-03 | A specialist raising a non-transient exception abstains immediately, contributes an empty section, and the consultation still completes with a real coordinator answer | G-3, B-2, B-3 | `tests/test_runtime_executor.py::test_one_specialist_raising_does_not_abort_the_others` |
| AC-007-04 | A specialist raising `LLMUnavailableError` once then succeeding is retried exactly once and completes normally | B-1 | `tests/test_runtime_executor.py::test_transient_model_failure_retries_then_succeeds` |
| AC-007-05 | The five frozen SSE events keep their pre-existing fields unchanged — this spec adds no new wire field | — | `tests/test_sse_contract.py`, `tests/test_workflow.py`, `tests/test_api_agents.py` (all pass unmodified) |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — recovery | `classify`/`decide_recovery` table | `tests/test_runtime_recovery.py` |
| Integration | retry-then-succeed, abstain-after-exhaustion, lifecycle/failure/recovery-action bookkeeping | `tests/test_runtime_executor.py` |
| Frozen (unaffected) | wire contracts unchanged — no new key this spec | `tests/test_sse_contract.py`, `tests/test_workflow.py`, `tests/test_api_agents.py` |

## 10. Migration & Compatibility

No shims — new code only (`src/sephiroth/runtime/recovery.py`). No
contract or wire-shape change. One frozen characterization test
(`test_one_specialist_raising_does_not_abort_the_others`) was
**deliberately rewritten**, not left "unmodified" — its own docstring said
outright that the old behavior (a raised exception aborts the whole
consultation) was a tracked gap, not a guarantee; this spec closes that
gap on purpose. The rewrite asserts the new, documented behavior instead
of deleting the coverage.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | `TOOL` category has no real trigger yet (NG-4) | Left in the transient set for symmetry with `MODEL`; harmless dead branch until tool execution can raise |
| 2 | A failed specialist's empty `AgentResult` still occupies a slot in `agent_outputs`/`agents_involved` | Deliberate (B-3) — the agent genuinely was selected and attempted; hiding it would misrepresent what the run actually did |
| 3 | Coordinator failures still propagate unchanged (NG-3) | Explicit scope cut — there is no fallback coordinator and no sensible partial answer without one; revisit only if a real incident shows this matters |
| 4 | `MAX_AGENT_ATTEMPTS=2` is a guess, not measured | Matches the pre-existing `PlanStep.max_attempts` default rather than inventing a new number; real tuning (recovery success rate, H4) needs eval data this environment can't generate |

## 12. References

- [ADR-007](../08-decisions/ADR-007-explicit-recovery.md)
- `docs/09-diagrams/architecture/D2-agent-lifecycle.md`
- `docs/specs/SPEC-006-telemetry.md` (spans/failures now both live on the same `RunState`)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. |
