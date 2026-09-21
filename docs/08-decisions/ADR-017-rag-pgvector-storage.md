# ADR-017 — Store the RAG corpus in pgvector, no in-memory fallback

**Status:** Accepted · **Date:** 2026-09-21 · **Phase:** decided 15, executed pending (SPEC-030)

## Context

The RAG corpus lives as two independently-edited artifacts today: the
document text as Python literals (`data/rag/__init__.py`,
`data/rag/corpus_primary_care.py`) and the document embeddings as a
separately-built, separately-committed JSON blob
(`data/embeddings/artifacts/seed_embeddings.json.gz`), loaded into an
in-memory vector store (`data/vectors/InMemoryVectorStore`) at process
start. `RAGPipeline` is deliberately designed to work with zero
configuration — no network, no DB — a property its own class docstring
states as a requirement.

Separately, `data/schemas/__init__.py` already carries a `GuidelineDocument`
model with a native pgvector `embedding` column, built during Phase 5 for
exactly this kind of storage — but never queried. `DEBT-003` tracked and
closed this as "intentional cold storage," documented rather than built.

## Problem

The decoupled corpus/artifact design is what let a real bug through
undetected: during the 2026-09-20 agent-reliability audit, the committed
embeddings artifact was built with one embedding model
(`nomic-embed-text`) while a different code path could compute a live
query embedding with another (`gemini-embedding-001`) — cosine similarity
compared across two unrelated vector spaces, silently wrong, with nothing
in the design to catch it. `SF051` closed the specific leak (local
providers can no longer reach a live Gemini client), but the structural
cause survives: nothing ties corpus text to its embedding except a
human remembering to rebuild the artifact after editing the Python
literals, and nothing prevents a future provider mismatch the same way.

Editing a guideline today means: edit a Python literal, then run a
separate script to rebuild the embeddings artifact, then commit both. A
mistake anywhere in that sequence produces silently stale embeddings, not
an error.

## Decision

Move both document text and document embeddings into
`guideline_documents` (already migrated, already pgvector-typed, never
used). `RAGPipeline.retrieve` becomes `async` and queries this table on
every call — a real DB round trip, not a cache warmed at process start.
No fallback to the in-memory/JSON path when Postgres is unreachable:
pgvector becomes the only backend, `InMemoryVectorStore` is deleted, and
`RAGPipeline()` requires a real `embedding_provider`.

## Rationale

- **A single row is a single source of truth.** Text and its embedding
  live together; there is no second artifact that can silently drift out
  of sync with the first, and no rebuild script standing between an edit
  and it taking effect.
- **The corpus becomes live-editable without a deploy.** A `guideline_documents`
  row can be corrected via a direct DB write and the very next query sees
  it — today, correcting a guideline needs a code change, a rebuilt
  artifact, and a redeploy.
- **This is exactly what the unused pgvector column was built for.**
  Closing `DEBT-003` by finally querying it costs less than maintaining a
  second, parallel storage mechanism (`data/vectors/`) indefinitely.
- **At 76 documents, "real DB query per call" costs nothing measurable.**
  The corpus is small and Postgres nearest-neighbor search on 76 rows is
  sub-millisecond regardless of index choice — the motivating win here is
  architectural (single source of truth), not throughput.
- **No fallback mode, by explicit choice, keeps the system simple to
  reason about.** A pipeline that silently degrades to keyword-only when
  the DB is unreachable hides exactly the kind of failure this decision
  exists to make loud — an unreachable Postgres should be a visible
  infrastructure incident, not a silent quality regression in retrieval.

## Consequences

- Every consultation's evidence lookup now has a hard dependency on
  Postgres being reachable. Accepted: the rest of the application already
  has this dependency (auth, patient data, consultation history) — RAG
  retrieval was the one path that didn't, for a reason (offline eval/tests)
  that this ADR judges no longer worth the cost of the decoupled-storage
  bug class it enabled.
- `python -m intelligence.evaluation.run --mode ci` and any test
  constructing a `RAGPipeline` now need a reachable Postgres to exercise
  real retrieval — mitigated by a skip-without-Postgres pattern
  (`tests/test_alembic_migration.py` already established this precedent;
  `SPEC-030` B-4 reuses it) rather than failing CI, which has no Postgres
  service.
- A one-time seed script must be run against every environment that needs
  real retrieval (local Postgres, Supabase) — a new required setup step,
  documented alongside `alembic upgrade head`.
- `data/vectors/` and the JSON-artifact-as-runtime-source code path are
  deleted, not kept as a shim — per `ADR-010`'s strangler-fig policy, a
  shim exists to protect an external caller during a migration; nothing
  outside `data/rag/__init__.py` constructs an `InMemoryVectorStore`
  directly, so there is nothing external to protect.

## Alternatives rejected

**Keep the in-memory store as a fallback when Postgres is unreachable** —
considered and explicitly rejected with the project owner: a silent
degrade-to-keyword-only on DB failure is exactly the kind of unnoticed
quality regression this decision exists to eliminate. An unreachable
database should surface as an infrastructure failure, not a worse answer
that looks like a normal one.

**Keep documents in Python, embeddings in pgvector, join at query time** —
rejected: this preserves the exact two-artifact split that caused the
original bug, just moving one half from a JSON file to a table. The
actual fix is collocating text and vector in the same row, not just
picking a different format for the vector half.

**Add a live ingestion API endpoint in the same change** — rejected as
scope creep (`SPEC-030` NG-1): nothing today has a validated need for
runtime guideline authoring, and building one is a separable decision with
its own auth/audit/validation surface. The seed script covers the actual
need (populate the table from the existing curated corpus).
