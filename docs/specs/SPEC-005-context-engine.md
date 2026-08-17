---
id: SPEC-005
title: Context Engine
phase: 4
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-003]
adrs: [ADR-011]
features: [F-034, F-035]
diagrams: [D1]
---

# SPEC-005 — Context Engine

## 1. Summary

Phase 4a: typed per-agent context views, lexical reranking, per-patient
consultation memory, and character-budget truncation
(`src/sephiroth/context/`). Sibling to `SPEC-004` (Verification & Safety,
Phase 4b) — both depend only on `SPEC-003`'s executor, not on each other,
per `docs/00-migration-charter.md` §7's dependency graph.

## 2. Motivation

Before this spec: every specialist received the exact same raw context
dict regardless of relevance (a `RadiologyAgent` got `lab_results` it never
reads); `RAGPipeline.retrieve()` had no post-fusion diversity step;
nothing bounded the coordinator's assembled prompt, built by concatenating
up to 4 specialist answers; and no consultation could recall anything about
the same patient's prior consultations. See `ADR-011` for the full
rationale and the alternatives rejected (a generic multi-turn session
abstraction, embedding-based reranking, a real tokenizer).

## 3. Goals

- **G-1** `AgentCapability.context_fields` lets an agent declare which
  `RunContext` fields it needs; `context_for_agent` enforces that
  projection at the executor's fan-out boundary.
- **G-2** `RAGPipeline.retrieve()` reranks its fused results for diversity
  via lexical MMR, with no new dependency and no embedding requirement.
- **G-3** A patient's most recent consultations are available to the
  coordinator (only) as `recent_consultations`, computed on the fly from
  the `Consultation` table.
- **G-4** The coordinator's assembled specialist sections, and each RAG
  result's content, are bounded to a character budget.

## 4. Non-Goals

- **NG-1** Generic conversational/session memory (multi-turn chat, a
  `conversation_id`). No validated product need exists; see `ADR-011`.
- **NG-2** Embedding-based reranking — the lexical MMR here must work
  identically whether or not an embedding provider is configured.
- **NG-3** A real tokenizer — character-count approximation only.
- **NG-4** Persisting `recent_consultations` anywhere — computed fresh per
  request from `Consultation`, never written back.
- **NG-5** Tuning `max_context_chars` or the MMR `lambda_mult` default
  against real data — both are placeholders, same status as `SPEC-004`'s
  confidence/abstention constants.

## 5. Definitions

- **Per-agent context view** — the subset of `RunContext` an agent actually
  receives, determined by its `AgentCapability.context_fields`.
- **Consultation memory** — short digests of a patient's own prior
  consultations, not a generic conversation history.

## 6. Contracts

### 6.1 Types

Module: `src/sephiroth/contracts/context.py` (new)

```python
class RunContext(BaseModel):
    medications: list[str]
    lab_results: dict[str, Any]
    image_path: str | None
    conditions: list[str]
    history: str
    recent_consultations: list[str]

    @classmethod
    def from_dict(cls, raw: dict | None) -> "RunContext": ...
```

Module: `src/sephiroth/contracts/capability.py` (existing, extended)

`AgentCapability` gains one field:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `context_fields` | `list[str]` | no | `[]` | `[]` means every `RunContext` field (backward compatible); non-empty names the only fields that agent receives |

### 6.2 Interfaces

```python
# src/sephiroth/context/views.py
def context_for_agent(capability: AgentCapability, ctx: RunContext) -> dict: ...
def log_filtered_fields(capability: AgentCapability, ctx: RunContext) -> None: ...


# src/sephiroth/context/rerank.py
def mmr_rerank(candidates: list[dict], lambda_mult: float = 0.7, top_k: int = 5) -> list[dict]: ...


# src/sephiroth/context/memory.py
async def recent_consultation_summaries(
    patient_id: str, session: AsyncSession, limit: int = 3
) -> list[str]: ...


# src/sephiroth/context/budget.py
def truncate(text: str, max_chars: int) -> str: ...
```

### 6.3 State machine

`N/A`.

### 6.4 Errors

None of the four functions raise on malformed input: `context_for_agent`
degrades to the full context if `context_fields` is empty; `mmr_rerank`
returns candidates unchanged if there are fewer than two; `truncate`
returns the input unchanged if under budget; `recent_consultation_summaries`
returns `[]` for an empty `patient_id` or no prior rows.

### 6.5 Configuration

| Setting | Module | Default | Status |
|---|---|---|---|
| `max_context_chars` | `platform/core/config.py` | 4000 | tunable (NG-5) |
| `lambda_mult` | `mmr_rerank` call site (`data/rag/__init__.py`) | 0.7 (function default) | tunable (NG-5) |

## 7. Behaviour

- **B-1** An agent whose `context_fields` is `[]` receives every `RunContext`
  field — no behavior change for a capability that declares nothing.
- **B-2** `mmr_rerank`'s top pick is always the highest-relevance candidate;
  only the ordering of subsequent picks trades relevance for diversity.
- **B-3** `recent_consultation_summaries` is called from the API router
  (`platform/api/routers/agents.py`), not the executor — the executor
  remains free of any DB dependency.
- **B-4** `recent_consultations` reaches only agents whose `context_fields`
  includes it or is empty — today, only the coordinator (every specialist
  has a non-empty `context_fields` that excludes it).
- **B-5** `truncate` cuts at the last word boundary before the limit, never
  mid-word.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-005-01 | `context_for_agent` returns every field for `context_fields=[]`, and only the declared subset otherwise | B-1 | `tests/test_context_views.py` |
| AC-005-02 | `mmr_rerank`'s first pick is always the highest-relevance candidate; a near-duplicate is deprioritized behind a dissimilar lower-scored candidate | B-2 | `tests/test_context_rerank.py` |
| AC-005-03 | `recent_consultation_summaries` returns `[]` for no `patient_id`/no rows, newest-first otherwise, scoped to the requested patient only | G-3 | `tests/test_context_memory.py` |
| AC-005-04 | `truncate` is a no-op under budget, cuts at a word boundary over budget | B-5 | `tests/test_context_budget.py` |
| AC-005-05 | `recent_consultations` injected by the router reaches the coordinator's prompt but not the evidence specialist's | B-3, B-4 | `tests/test_api_agents.py` |
| AC-005-06 | The full pre-existing test suite (including the three frozen contract files) passes unmodified after the executor switched to enforcing `context_for_agent` | ADR-011's rollout rationale | `tests/test_workflow.py`, `tests/test_sse_contract.py`, `tests/test_api_agents.py`, `tests/test_runtime_executor.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — views | field projection | `tests/test_context_views.py` |
| Unit — rerank | MMR selection order | `tests/test_context_rerank.py` |
| Unit — memory | patient-scoped query, DB fixture | `tests/test_context_memory.py` |
| Unit — budget | truncation | `tests/test_context_budget.py` |
| Integration | per-agent view reaching only the intended agent, end to end | `tests/test_api_agents.py::test_recent_consultations_reach_only_the_coordinator` |
| Regression | RAGPipeline ranking after MMR | `tests/test_rag_pipeline.py` (one assertion relaxed, documented inline) |
| Frozen (unaffected) | wire/persistence contracts | `tests/test_sse_contract.py`, `tests/test_workflow.py`, `tests/test_api_agents.py` |

## 10. Migration & Compatibility

No shims — this is entirely new code (`src/sephiroth/context/`,
`src/sephiroth/contracts/context.py`). `AgentCapability.context_fields` is
additive (default `[]`), so every pre-existing capability record not
updated in this PR would fall back to "every field" automatically — in
practice all five records in `src/sephiroth/runtime/registry.py` were
given real values in this same phase.

`data/rag/__init__.py::RAGPipeline._finalize` imports from `sephiroth.context`
— the first time `data/` has depended on `src/sephiroth/`. Not a violation
of any strangler-fig rule (those govern the legacy→sephiroth migration
direction and shim deletion schedule, not general import direction); noted
here for visibility since it's a new pattern.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | The permissive-then-enforcing rollout the charter calls for (§9) was validated via the full test suite, not a live eval run with real logs | Documented explicitly in `ADR-011` as an environment-driven adaptation, not a silent skip; `log_filtered_fields` remains available for a future live observation window if capability context needs change |
| 2 | `max_context_chars` (4000) and MMR's `lambda_mult` (0.7) are untuned placeholders | Same status as `SPEC-004`'s confidence/abstention constants — flagged, not data-driven yet (NG-5) |
| 3 | `data/rag` now depends on `src/sephiroth/context` — a new import direction | Assessed as architecturally acceptable (no cycle, `sephiroth.context` has no heavy deps); not expected to complicate a future `data/rag` → `sephiroth` migration |

## 12. References

- [ADR-011](../08-decisions/ADR-011-context-engine.md)
- `docs/01-architecture/overview.md` (Context Engine layer description)
- `docs/00-migration-charter.md` §7 (phase dependency graph), §9 (two-commit rollout requirement)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. |
