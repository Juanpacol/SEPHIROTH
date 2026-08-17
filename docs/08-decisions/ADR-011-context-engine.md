# ADR-011 — Context Engine: scoped to what has a real hook today

**Status:** Accepted · **Date:** 2026-08-19 · **Phase:** decided and executed 4a

## Context

`docs/01-architecture/overview.md`'s target layer table names Context Engine
as "Retrieval, ranking, memory, compression, budgeting." Before this ADR,
zero code existed for any of the four: every specialist received the exact
same raw context dict regardless of relevance, `RAGPipeline.retrieve()` had
no post-fusion reranking step, nothing bounded the size of the coordinator's
assembled prompt, and there was no multi-turn or session concept anywhere in
the stack — each `/consult` call is 100% stateless.

## Decision

Build all four capabilities, each scoped to the simplest thing that
satisfies a real, already-existing need — not a speculative platform:

1. **Per-agent context views** (`src/sephiroth/contracts/context.py::RunContext`,
   `src/sephiroth/context/views.py::context_for_agent`) — `AgentCapability`
   declares `context_fields`; the executor projects `RunContext` down to
   only those before calling an agent.
2. **Reranking** (`src/sephiroth/context/rerank.py::mmr_rerank`) — lexical
   Maximal Marginal Relevance (token-overlap similarity, not embeddings) so
   it works identically in `RAGPipeline`'s keyword-only degraded mode.
3. **Memory** (`src/sephiroth/context/memory.py::recent_consultation_summaries`)
   — scoped to "this patient's own recent consultations," not a generic
   conversational session. See the rejected alternative below.
4. **Token budgeting** (`src/sephiroth/context/budget.py::truncate`) —
   character-count approximation, not a real tokenizer.

## Rationale

- **Memory scoped to `patient_id`, not a new session/thread concept.**
  There is no validated product need for multi-turn chat memory today — the
  frontend doesn't send prior turns, `Consultation` has no `session_id`, and
  building one from scratch (frontend changes, a new identifier, wiring
  through every layer) would be exactly the premature complexity this
  project's engineering discipline avoids. `patient_id` already links every
  consultation to a patient and already has a real clinical justification:
  recalling what was asked and answered about the same patient before is
  useful; recalling unrelated chit-chat turns is not a need anyone has
  asked for yet.
- **Reranking without embeddings.** `RAGPipeline` must keep working with
  zero configuration (no network, no API key) — a reranker requiring
  embeddings would silently no-op in that mode. Token-overlap MMR works
  identically in both the keyword-only and hybrid paths.
- **Character-count budgeting, not a tokenizer.** No new dependency, and
  the actual problem (an unbounded concatenation of up to 4 specialist
  answers feeding the coordinator prompt) doesn't need token-exact
  precision to fix — it needs a bound.
- **Per-agent views enforced directly, not staged as two separate commits.**
  The migration charter (§9) calls for a permissive-then-enforcing rollout
  for this specific change, historically done via a live eval run showing
  zero denials (Phase 0's tool-authorization pattern). This session has no
  live model access to reproduce that literally; the equivalent evidence
  used instead was the full pre-existing test suite — including the three
  frozen contract test files (`test_workflow.py`, `test_sse_contract.py`,
  `test_api_agents.py`) — passing unmodified after switching straight to
  enforcing, which is only possible if no agent depended on a context field
  outside its declared `context_fields`. `log_filtered_fields` still exists
  as a standalone, tested utility for any future observation window if
  capability context needs change.

## Consequences

- `RAGPipeline.retrieve()`'s output is no longer guaranteed strictly
  descending by score past the top hit (MMR trades relevance-order for
  diversity) — `tests/test_rag_pipeline.py::test_retrieve_ranks_more_relevant_document_first`
  updated to check only that the single most relevant document still ranks
  first.
- `recent_consultation_summaries` is called from the API router
  (`platform/api/routers/agents.py`), not the executor — the executor
  stays free of any DB dependency, unchanged from its existing design.
- Confidence/abstention weight tuning (SPEC-004 NG-3) is unaffected by this
  ADR — Context Engine and Verification & Safety are independent siblings
  per the migration charter's dependency graph.

## Alternatives rejected

**Generic conversational memory (a `conversation_id`/session abstraction,
frontend changes to replay prior turns)** — no validated product need
exists yet; building the abstraction speculatively is the premature
complexity `docs/00-project/scope.md` warns against. Revisit once a real
multi-turn chat UX is scoped as its own feature.
**Embedding-based (MMR-over-vectors) reranking** — would only work when an
embedding provider is configured, silently regressing to a no-op in
`RAGPipeline`'s zero-configuration keyword-only mode.
**A real tokenizer for budgeting** — precision no scenario here actually
needs; adds a dependency for no measured benefit over character counts.
