---
id: SPEC-006
title: Telemetry — Trace-Based Observability
phase: 5
version: 1.1.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-21
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-003, SPEC-004]
adrs: [ADR-009]
features: [F-042, F-043]
diagrams: [D1]
---

# SPEC-006 — Telemetry: Trace-Based Observability

## 1. Summary

Executes `ADR-009`: every consultation now emits a structured, replayable
`ExecutionTrace` (`sephiroth.contracts.trace`, defined since Phase 0, unused
until now) and persists it. Real spans are recorded for two of `ADR-009`'s
four named seams — `Executor.step` and `Verifier.check` — with the other
two (`ModelProvider.chat`, `ToolRuntime.execute`) deliberately deferred, see
§4/§10.

## 2. Motivation

Before this spec, observability was `logger.info` lines and a
template-based `explainability.py` audit trail derived from persisted
tool calls — neither is a property of *one execution* that can be
aggregated to answer "what fraction of runs abstained?" or "what's the p95
agent latency?" `ADR-009` calls the trace "the measurement instrument,"
not a debugging aid — this spec is where that instrument gets built.

## 3. Goals

- **G-1** `build_trace(state) -> ExecutionTrace` projects a fully-populated
  `RunState` into the persisted trace contract, reusing its fields
  directly (no re-derivation of evidence/claims/citations/abstention).
- **G-2** Real spans for `Executor.step` (one per agent turn) and
  `Verifier.check` (the claim-verification/abstention pass), respecting
  the redaction allow-list already enforced by `Span`'s own constructor.
- **G-3** `settings.enable_tracing` toggles tracing without changing any
  other observable output — the H6 requirement (`ADR-009`): a run with
  tracing off must produce an identical result to one with it on, apart
  from the trace/spans.
- **G-4** Persist the trace as one nullable JSON column plus the 4 indexed
  scalars `ADR-009` names: `trace_id`, `risk_level`, `abstained`,
  `supported_claim_ratio`.

## 4. Non-Goals

- **NG-1** *(partially closed, v1.1.0 — SPEC-016)* Independent live spans
  for `ModelProvider.chat` and `ToolRuntime.execute` as their own
  `SpanKind.MODEL`/`SpanKind.TOOL` intervals. Still not built, and for
  the reason originally given: `ToolRuntime` is a shared singleton with
  no per-request state — threading one through would change
  `ToolExecutor`'s `Callable` signature that `FakeLLMClient` and every
  `scoped_executor()` call site already depend on. What v1.1.0 *does*
  add: the existing `Executor.step` (`SpanKind.AGENT`) span now carries
  a real `model` attribute, and — more importantly — `AgentResult`
  (including the coordinator's own call, via the new
  `RunState.coordinator_result`) carries real `prompt_tokens`/
  `completion_tokens`/`latency_ms` from the actual provider response,
  not a placeholder. A genuinely independent `MODEL` span is still
  future work, justified once an agent makes more than one `chat()`
  call per turn (today `Executor.step` already bounds the single call
  as tightly as a nested span would).
- **NG-2** *(closed, v1.1.0 — SPEC-016)* Token/cost accounting.
  `ChatResult` now carries real `prompt_tokens`/`completion_tokens` from
  `GeminiClient` (`response.usage_metadata`) and `GroqClient`
  (`data["usage"]`, OpenAI-compatible shape), summed across every round
  of the tool-calling loop and plumbed through `AgentResult` into
  `ExecutionTrace.tokens`. `cost_usd` is a best-effort estimate from a
  hand-maintained price table (`src/sephiroth/telemetry/pricing.py`) —
  not a billing source of truth, and `0.0` for a model the table doesn't
  recognize rather than a guess. **Still not covered:** `generate_json`
  calls (claim extraction, verification, the dynamic planner) don't go
  through `ChatResult` and report no usage — a real, separate, and
  smaller gap than the one this closes, since those calls are one-shot
  and typically far cheaper than the main `chat()` loop.
- **NG-3** A pluggable `Tracer`/OTel emitter Protocol. `ADR-009` allows one
  ("OTel remains available as an emitter"), but building the abstraction
  now, with a single in-process consumer (Postgres JSON column) and no
  second backend to swap to, is exactly the premature complexity this
  project avoids. `traced_span` writes directly to `RunState.spans`; a
  Protocol can be introduced when a real second backend exists.
- **NG-4** Exposing the trace's SSE representation for anything beyond
  additive persistence — the frontend doesn't render it yet; this spec
  only makes the data exist and be queryable.

## 5. Definitions

- **Span** — one instrumented interval (`sephiroth.contracts.trace.Span`),
  attributes allow-listed at construction.
- **Trace** — the complete, replayable record of one consultation
  (`ExecutionTrace`), built once at the end of a run.

## 6. Contracts

### 6.1 Types

No contract types change shape. `RunState` (existing, Phase 0) gains one
additive field:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `spans` | `list[Span]` | no | `[]` | Populated by `traced_span`; empty when `enable_tracing` is `False` |

`Consultation` (`data/schemas/__init__.py`) gains 5 columns, all nullable:
`trace: JSON`, `trace_id: str(64)`, `risk_level: str(20)`, `abstained: bool`,
`supported_claim_ratio: float` — the last 4 indexed, per `ADR-009`.

### 6.2 Interfaces

```python
# src/sephiroth/telemetry/span.py
@contextmanager
def traced_span(state: RunState, kind: SpanKind, name: str, **attrs) -> Iterator[None]: ...


# src/sephiroth/telemetry/build_trace.py
def build_trace(state: RunState, model: str = "", provider: str = "") -> ExecutionTrace: ...
```

### 6.3 State machine

`N/A`.

### 6.4 Errors

`traced_span` never raises on its own — an exception inside the wrapped
block is recorded as `ok=False` and re-raised unchanged, so instrumentation
never masks or replaces a real failure. Attributes outside
`ALLOWED_SPAN_ATTRIBUTES` are silently dropped, not raised — this differs
from `Span`'s own strict constructor (which raises on a disallowed key),
deliberately: instrumentation call sites must never break a consultation
over a stray keyword; the allow-list is still fully enforced, just failing
closed by omission instead of by exception at this one call boundary.

### 6.5 Configuration

| Setting | Module | Default | Status |
|---|---|---|---|
| `enable_tracing` | `platform/core/config.py` | `True` | stable |

## 7. Behaviour

- **B-1** `traced_span` records exactly one `Span` per invocation when
  tracing is enabled, timed with `time.monotonic()`, `ok=True` unless the
  wrapped block raised.
- **B-2** `traced_span` is a pure no-op (beyond running the wrapped block)
  when `enable_tracing` is `False` — no `Span` is appended, no attribute
  filtering runs.
- **B-3** `build_trace` constructs a `VerificationReport` from
  `state.claims`/`state.contradictions` only when at least one exists;
  otherwise `ExecutionTrace.verification` is `None`.
- **B-4** `run_consultation`/`stream_consultation`'s `final` event and
  return dict gain `trace` as an additive, optional key — the five frozen
  SSE events keep identical shape/casing otherwise.
- **B-5** `_persist` derives `abstained`/`risk_level`/`trace_id` from the
  trace, and `supported_claim_ratio` from the `verification_report`'s
  claim statuses directly (not from `VerificationReport`'s `@property`,
  which isn't a serialized field — see §10).

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-006-01 | `traced_span` appends a `Span` with correct `trace_id`/`kind`/`name`/`ok`/filtered `attributes` when enabled | B-1 | `tests/test_telemetry_span.py` |
| AC-006-02 | `traced_span` re-raises the original exception and still records `ok=False` | §6.4 | `tests/test_telemetry_span.py` |
| AC-006-03 | `traced_span` is a no-op when `enable_tracing=False` | B-2 | `tests/test_telemetry_span.py` |
| AC-006-04 | Disallowed span attributes are dropped, not raised | §6.4 | `tests/test_telemetry_span.py` |
| AC-006-05 | `build_trace` projects `RunState` correctly, including the conditional `VerificationReport` | B-3 | `tests/test_telemetry_build_trace.py` |
| AC-006-06 | A consultation run with tracing enabled vs. disabled produces an identical result apart from `trace`/`spans` (ADR-009 H6) | G-3 | `tests/test_runtime_executor.py::test_tracing_on_vs_off_produces_an_identical_run_apart_from_the_trace` |
| AC-006-07 | The five frozen SSE events keep their pre-existing fields unchanged; `trace` is additive only | B-4 | `tests/test_sse_contract.py` (additively extended, not altered) |
| AC-006-08 | `GeminiClient`/`GroqClient` report real `prompt_tokens`/`completion_tokens` on `ChatResult`, summed across tool-calling rounds, `0` when the response carries no usage metadata | NG-2 closure | `tests/test_gemini_client.py::test_chat_reports_real_usage_when_present`, `::test_chat_sums_usage_across_tool_rounds`, `::test_chat_usage_defaults_to_zero_when_absent`, `tests/test_groq_client.py::test_chat_reports_real_usage_when_present`, `::test_chat_usage_defaults_to_zero_when_absent` |
| AC-006-09 | `ExecutionTrace.tokens`/`.cost_usd` reflect every specialist's real usage *and* the coordinator's, without the coordinator appearing in `agents_involved` | NG-2 closure | `tests/test_telemetry_build_trace.py::test_latency_and_tokens_summed_from_agent_results`, `::test_cost_estimated_from_known_model_pricing`, `::test_cost_is_zero_for_unrecognized_model`, `tests/test_runtime_executor.py::test_trace_tokens_include_both_specialists_and_coordinator` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — span | recording, no-op, exception handling, redaction | `tests/test_telemetry_span.py` |
| Unit — build_trace | projection from `RunState`, conditional verification | `tests/test_telemetry_build_trace.py` |
| Integration | tracing on/off parity (H6) | `tests/test_runtime_executor.py` |
| Migration | new columns applied against a clean local Postgres | `tests/test_alembic_migration.py` |
| Frozen (additive only) | wire contracts unchanged in existing fields | `tests/test_sse_contract.py`, `tests/test_api_agents.py`, `tests/test_workflow.py` (untouched) |

## 10. Migration & Compatibility

No shims — new code only (`src/sephiroth/telemetry/`). `RunState.spans` is
additive (default `[]`); any code constructing a `RunState` without it
continues to work.

**Friction found during implementation**: `VerificationReport.supported_claim_ratio`
is a Pydantic `@property`, not a `computed_field` — it does **not** appear
in `model_dump()`'s output. `_persist` in `platform/api/routers/agents.py`
recomputes it directly from `verification_report["claims"]`'s `status`
values (already present in the frozen wire shape) rather than reading it
off the serialized trace dict, which would have silently been `None`
forever. Documented here rather than silently worked around, per this
project's standing discipline.

`explainability.py::build_explanation`'s "one readable step per tool call"
logic is **not yet** reimplemented as a projection of `ExecutionTrace.spans`
— that migration is `DEBT-010`'s sibling (relocating
`risk_engine.py`/shimming `citation_guard.py`/`explainability.py`), tracked
as its own follow-up cycle, not part of this spec.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Only 2 of `ADR-009`'s 4 named seams get an independent `Span` this cycle | Explicit non-goal (NG-1) — real token/model *data* now flows (v1.1.0), but not as separate `MODEL`/`TOOL` span intervals; the API friction blocking that is unchanged |
| 2 | ~~Token/cost fields on the trace are placeholders (always 0 today)~~ Closed in v1.1.0 (SPEC-016) — see NG-2 | `generate_json` calls still report no usage (claim extraction, verification, dynamic planner) — smaller, separate gap |
| 3 | No pluggable Tracer/OTel backend | Explicit non-goal (NG-3) — premature with a single consumer; `opentelemetry-api` is already present in the environment (a transitive dependency) but not wired to anything |
| 4 | `explainability.py` still hand-rolls its own audit trail instead of reading `ExecutionTrace.spans` | Tracked as a follow-up alongside the `risk_engine.py` relocation cycle, not this spec |

## 12. References

- [ADR-009](../08-decisions/ADR-009-trace-based-observability.md)
- `src/sephiroth/contracts/trace.py` (the pre-existing contract this spec finally uses)
- `docs/00-migration-charter.md` §7 (Phase 5 — Observability + shim removal)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. |
| 1.1.0 | 2026-08-21 | Closes NG-2 (real token/cost, `GeminiClient`/`GroqClient` usage metadata + `pricing.py`); partially advances NG-1 (real `model`/token/latency data on the existing `AGENT` span and `AgentResult`, incl. the coordinator via new `RunState.coordinator_result` — still no independent `MODEL`/`TOOL` span). Additive only — see AC-006-08/09. |
