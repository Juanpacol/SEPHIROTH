---
id: SPEC-030
title: RAG Document Storage on pgvector
phase: 15
version: 0.1.0
status: Approved
authors: [jbotero]
created: 2026-09-21
updated: 2026-09-21
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-002]
adrs: [ADR-017]
features: [F-006]
diagrams: []
---

# SPEC-030 — RAG Document Storage on pgvector

## 1. Summary

Moves the RAG corpus's documents and embeddings from two decoupled sources
— Python literals (`data/rag/__init__.py`, `data/rag/corpus_primary_care.py`)
and a separately-built, separately-committed JSON artifact
(`data/embeddings/artifacts/seed_embeddings.json.gz`) — into the single
Postgres table that already exists for exactly this purpose but has never
been queried: `GuidelineDocument`/`guideline_documents`
(`data/schemas/__init__.py:492-519`, pgvector, 768-dim). `RAGPipeline.retrieve`
becomes `async` and queries this table directly on every call — a real DB
round trip per retrieval, not a cache warmed at process start.

## 2. Motivation

`data/rag/__init__.py:964` documents `RAGPipeline`'s own contract in its
class docstring: *"Fully functional with zero configuration... no network
or DB."* That design choice is exactly what let a real bug through
undetected during the 2026-09-20 agent-reliability audit (`SF051`): the
committed embeddings artifact was built with one embedding model
(`nomic-embed-text` via Ollama) while a different code path could compute a
live query embedding with another (`gemini-embedding-001`) — cosine
similarity compared across two unrelated vector spaces, silently. `SF051`
fixed the specific leak path (local providers can no longer reach a live
Gemini client), but the structural cause — corpus text and corpus vectors
living in two independently-edited artifacts with no schema tying them
together — is unchanged and can recur the same way for a different
provider pairing.

`data/schemas/__init__.py:492-497` already names this precisely:
`GuidelineDocument` "persists a pgvector column that is never queried" —
tracked and closed as `DEBT-003` in Phase 5, but closed by *documenting*
the gap as intentional, not by building the read path. This spec builds
that read path.

## 3. Goals

- **G-1** Corpus text and its embedding live in one row of one table —
  editing either is one write, not "edit a Python literal, then remember
  to rerun a separate artifact-rebuild script."
- **G-2** `RAGPipeline.retrieve` reads current database state on every
  call — no in-process cache that can silently diverge from the DB, and no
  redeploy needed to pick up a corrected guideline.
- **G-3** Preserve retrieval *behavior* exactly: the same hybrid
  keyword+dense RRF fusion, the same MMR diversity rerank, the same
  citation shape, the same `min_similarity` floor
  (`settings.retrieval_min_similarity`) — this spec changes *where data
  lives and how it's queried*, not the ranking algorithm.
- **G-4** Close `DEBT-003` for real: `guideline_documents` becomes the
  live source of truth, not cold storage.

## 4. Non-Goals

- **NG-1** No ingestion API endpoint. Seeding is a one-time script
  (`data/rag/seed_pgvector.py` or equivalent), run manually the same way
  `data.embeddings.build_artifact` is today — not a route a clinician or
  admin calls. A real ingestion UI is future work with no validated need
  yet (matches the original `DEBT-003` reasoning).
- **NG-2** No change to corpus *content* — the 76 documents move as-is.
  Expanding coverage (the plan's original Fase 4 step 5) is separate,
  optional future work, not gated on this spec.
- **NG-3** No HNSW/IVFFlat tuning beyond adding one basic index. At 76
  rows, index choice has no measurable performance effect; revisit if the
  corpus grows by an order of magnitude.
- **NG-4** No change to `EmbeddingProvider`'s protocol or its use for
  *query*-side embedding (`embed_query`) — a user's free-text question
  still can't be precomputed and still goes through
  `CachedEmbeddingProvider`/a live provider exactly as today. Only the
  *document*-side embeddings (`embed_documents`, computed once at seed
  time) move storage location.
- **NG-5** No fallback to the in-memory/JSON-artifact path when Postgres
  is unreachable — confirmed with the project owner: pgvector becomes the
  only backend. `data/vectors/InMemoryVectorStore` and the keyword-only
  "no embedding_provider" mode are removed, not kept as a degraded mode.

## 5. Definitions

- **Seed script** — the one-time (or re-run-on-demand) script that reads
  `SEED_GUIDELINES` + `PRIMARY_CARE_GUIDELINES` and the current embedding
  provider, and upserts each into `guideline_documents`. The initial
  population mechanism, not a runtime dependency.
- **DB-dependent test** — any test that constructs a `RAGPipeline` (or
  calls code that does) and therefore needs the seeded
  `guideline_documents` table to exist and be reachable.

## 6. Contracts

### 6.1 Types

Module: `data/schemas/__init__.py` — `GuidelineDocument` is unchanged in
shape (no migration needed for the table itself; it already matches this
spec's needs). Its docstring is rewritten to remove the "never queried,
cold storage" framing.

Module: `data/rag/document.py` — `Document` (the in-memory dataclass
`RAGPipeline` returns to callers) is unchanged; it is now constructed from
a `GuidelineDocument` row instead of a Python literal.

### 6.2 Interfaces

Module: `data/rag/__init__.py`

```python
class RAGPipeline:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        min_similarity: float = 0.636,
        session_factory: Callable[[], AsyncContextManager[AsyncSession]] | None = None,
    ): ...
    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]: ...
    async def add_document(self, doc: Document) -> None: ...


class MedicalKnowledgeBase:
    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]: ...
```

`embedding_provider` becomes required (no default `None`) — a
`RAGPipeline` with no way to embed a query can no longer do a keyword-only
retrieval as a legal degraded mode (NG-5); construction fails loudly
instead (`TypeError` for the missing argument) rather than silently
degrading. `seed`/`vector_store` constructor parameters are removed —
there is no longer an alternative document source or vector backend to
choose between.

Module: `intelligence/mcp/rag_server.py`

```python
async def list_evidence_categories() -> Dict[str, int]: ...
async def list_evidence_by_category(category: str) -> List[Dict[str, Any]]: ...


@mcp.tool
async def search_clinical_guidelines(query: str, top_k: int = MAX_GUIDELINE_RESULTS) -> Dict[str, Any]: ...
```

All three become `async` (were sync) — each now does a real query.
`ToolRuntime.execute`/`scoped_executor` already dispatch async tool
functions transparently (`search_pubmed` is the existing precedent); no
change needed there.

**New module:** `data/rag/seed_pgvector.py` — the seed script (NG-1).

```python
async def seed_from_python_corpus(embedding_provider: EmbeddingProvider) -> int:
    """Upserts every Document in SEED_GUIDELINES into guideline_documents.
    Returns the number of rows written. Idempotent — re-running updates
    existing rows by id rather than duplicating them."""
```

### 6.3 State machine

`N/A` — no lifecycle beyond "query, get results."

### 6.4 Errors

A `RAGPipeline.retrieve` call against an unreachable/unmigrated database
propagates the underlying `sqlalchemy`/`asyncpg` exception — this is a
genuine infrastructure failure, not a "fall back to keyword-only" case
(that degraded mode no longer exists, NG-5). Callers (the MCP tool
dispatch, `ToolRuntime.scoped_executor`) already convert an unhandled
tool exception into the existing `{"error": ...}` tool-result shape or the
executor's `ToolCallOmittedError`/recovery path (`SPEC-007`) — no new
error type is introduced by this spec.

### 6.5 Configuration

`N/A` — no new settings. `settings.database_url` (already required) is now
also RAG's connection string; `settings.retrieval_min_similarity` is
unchanged.

## 7. Behaviour

- **B-1** `RAGPipeline.retrieve` MUST query `guideline_documents` fresh on
  every call — no corpus or embedding state cached across calls in the
  pipeline instance.
- **B-2** Keyword scoring, RRF fusion, MMR reranking, and the citation
  shape returned to callers MUST be byte-for-byte identical in behavior to
  the pre-migration implementation for the same corpus content and query
  (parity, not just "returns something").
  `tests/test_rag_pipeline.py`/`tests/test_embeddings_matching.py`'s
  existing assertions are the parity gate.
- **B-3** The seed script MUST be idempotent — running it twice against
  the same corpus content leaves `guideline_documents` in the same state
  as running it once (upsert by `id`, not insert-only).
- **B-4** A test that requires `guideline_documents` to be seeded MUST
  skip, not fail, when no local Postgres is reachable — the same pattern
  `tests/test_alembic_migration.py` already uses (`SPEC-000` NG-2 doesn't
  require a new pattern here, just its reuse).
- **B-5** `python -m intelligence.evaluation.run --mode ci` MUST report a
  clear "retrieval metrics skipped — no database" status (not a raw
  traceback) when Postgres is unreachable, since CI's `eval` job
  (`.github/workflows/code-review.yml`) has no Postgres service.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-030-01 | `RAGPipeline()` requires `embedding_provider`; omitting it is a `TypeError` | §6.2 | `tests/test_rag_pipeline.py` |
| AC-030-02 | Given a seeded `guideline_documents` table, `retrieve()` returns the same top-k ids/order as the pre-migration in-memory pipeline for every case in `intelligence/evaluation/datasets/golden.json` | B-2 | `tests/test_embeddings_matching.py` |
| AC-030-03 | `seed_from_python_corpus` run twice leaves `guideline_documents`'s row count and content unchanged after the second run | B-3 | `tests/test_rag_seed.py` (new) |
| AC-030-04 | Every DB-dependent RAG test skips (not fails, not errors) when `localhost:5433` is unreachable | B-4 | `tests/test_rag_pipeline.py`, `tests/test_embeddings_matching.py` |
| AC-030-05 | `run --mode ci` prints a "SKIPPED — no database" retrieval-metrics line and exits without a traceback when Postgres is unreachable | B-5 | `tests/test_evaluation.py` |
| AC-030-06 | `data/vectors/` (`InMemoryVectorStore`) has no importer left anywhere under `src/`, `intelligence/`, `platform/`, `data/` | NG-5 | `tests/test_no_in_memory_vector_store.py` (new) |
| AC-030-07 | `search_clinical_guidelines`, `list_evidence_categories`, `list_evidence_by_category` are all `async def` | §6.2 | `tests/test_mcp.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — pipeline | Keyword scoring, RRF fusion, MMR rerank against a seeded test DB | `tests/test_rag_pipeline.py` |
| Matching quality | Real embedding-model recall/precision against golden cases | `tests/test_embeddings_matching.py` |
| Seed script | Idempotency, round-trip content fidelity | `tests/test_rag_seed.py` (new) |
| Dependency hygiene | No lingering import of the removed in-memory backend | `tests/test_no_in_memory_vector_store.py` (new) |
| Eval harness | Graceful skip without a DB | `tests/test_evaluation.py` |
| MCP contract | Tools are async, dispatch unaffected | `tests/test_mcp.py`, `tests/test_tool_authorization.py` |

## 10. Migration & Compatibility

**No schema migration for `guideline_documents` itself** — the table,
columns, and `Vector(768)` type already exist in the baseline migration
(`migrations/versions/dff332c99951_initial_schema.py`) and in Supabase (it
was created by the same `create_all`-then-stamped baseline every other
table was). This spec adds one migration: an IVFFlat (or HNSW, decided at
implementation time based on what the installed pgvector version
supports) index on `guideline_documents.embedding`, currently absent by
design per that model's own docstring.

**Strangler-fig (`ADR-010`):** `data/vectors/` (`InMemoryVectorStore`,
`VectorStore` protocol) and the JSON-artifact-as-runtime-source path
(`data/embeddings/cached.py`'s use *for documents*, not queries) are
deleted outright once the seed script and pgvector-backed `retrieve()` are
live and parity-tested — confirmed with the project owner that no fallback
mode is wanted (NG-5), so a shim here would protect a mode nobody wants
kept. `CachedEmbeddingProvider` itself is **not** deleted — it's still how
a query's embedding gets computed deterministically offline
(`embed_query`), which is unrelated to where *document* embeddings live.

**One-time data migration:** the seed script must run once against every
environment that needs real retrieval — local Postgres (docker-compose)
and Supabase. Documented as a required step in `README.md`'s setup section
and `docker-compose.yml`'s backend startup notes, the same way
`alembic upgrade head` already is.

**Breaks the "tests need no services" promise for RAG-touching tests.**
Confirmed with the project owner: acceptable, mitigated by B-4's
skip-without-Postgres pattern (already precedented by
`test_alembic_migration.py`). `README.md`'s testing section gets a
one-line amendment noting the RAG-specific exception.

## 11. Risks & Open Questions

| # | Risk / question | Resolution / ADR |
|---|---|---|
| 1 | Every retrieval now costs a real DB round trip instead of an in-process lookup | Accepted per `ADR-017`: at 76 rows the query is sub-millisecond; the motivating win (single source of truth, live-editable corpus) is architectural, not a performance concern at this scale. |
| 2 | `--mode ci` (previously genuinely offline) now needs Postgres, weakening its "zero-config eval" value proposition | Mitigated by B-5's graceful skip — the eval still runs and reports every metric that doesn't need retrieval; only recall/MRR/citation-precision report "skipped" without a DB, same tier of degradation the eval already tolerates for `faithfulness_llm_judge` when the baseline is stale. |
| 3 | IVFFlat vs. HNSW choice | Deferred to implementation: whichever the installed `pgvector` extension version on Supabase supports without an extra `CREATE EXTENSION` step beyond what's already enabled; either is fine at this corpus size (NG-3). |

## 12. References

- [ADR-017](../08-decisions/ADR-017-rag-pgvector-storage.md)
- [ADR-010](../08-decisions/ADR-010-runtime-separate-from-application.md) — strangler-fig shim policy
- `docs/specs/SPEC-002-tool-runtime.md` — `ToolRuntime`'s async-tool dispatch, unchanged by this spec
- `docs/project-state.yaml` DEBT-003

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-09-21 | Initial draft |
| 0.1.0 | 2026-09-21 | Approved — human review confirmed the no-fallback pgvector-only design and the full SDD process before writing tests |
