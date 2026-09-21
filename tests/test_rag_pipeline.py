"""Tests for the RAG pipeline: pure keyword/RRF-fusion logic (no database),
and the pgvector-backed `retrieve()` end to end (SPEC-030/ADR-017, Phase 15
— needs a real Postgres, since SQLite has no pgvector equivalent; skips
automatically without one, same pattern as `tests/test_alembic_migration.py`).
"""

import socket

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from data.embeddings.base import EmbeddingUnavailable
from data.rag import SEED_GUIDELINES, Document, MedicalKnowledgeBase, RAGPipeline, ScoredDoc, _fuse, _tokenize
from data.rag import _retrieve_keyword as retrieve_keyword


def test_rag_pipeline_requires_an_embedding_provider():
    """AC-030-01: SPEC-030/ADR-017 removes the keyword-only degraded mode
    (NG-5, no fallback) — a `RAGPipeline` with no way to embed a query can
    no longer be constructed at all, so omitting `embedding_provider` must
    fail loudly (`TypeError`) rather than silently constructing a
    keyword-only pipeline the way it does today."""
    with pytest.raises(TypeError):
        RAGPipeline()


def test_tokenize_lowercases_and_drops_stopwords():
    tokens = _tokenize("What A1C Goal is appropriate for the patient?")
    assert "what" not in tokens
    assert "the" not in tokens
    assert "for" not in tokens
    assert "a1c" in tokens
    assert "goal" in tokens


def test_tokenize_empty_or_stopword_only_query_returns_empty():
    assert _tokenize("") == []
    assert _tokenize("the a an of for") == []


def test_document_citation_with_full_metadata():
    doc = Document(
        id="x",
        content="content",
        source="Some Source",
        metadata={"organization": "ACME Org", "year": 2020, "title": "The Title"},
    )
    assert doc.citation == "The Title, ACME Org, 2020"


def test_document_citation_without_metadata_falls_back_to_source():
    doc = Document(id="x", content="content", source="Fallback Source")
    assert doc.citation == "Fallback Source"


def test_seed_corpus_integrity():
    ids = [doc.id for doc in SEED_GUIDELINES]
    assert len(ids) == len(set(ids)), "duplicate document ids in SEED_GUIDELINES"
    assert len(SEED_GUIDELINES) >= 20
    for doc in SEED_GUIDELINES:
        assert doc.metadata.get("organization")
        assert doc.metadata.get("year")


# --------------------------------------------------------------------------
# Pure logic — keyword scoring + RRF fusion, no database (SPEC-030 §6.2
# extracted these as free functions of an explicit document list precisely
# so they stay unit-testable without pgvector).
# --------------------------------------------------------------------------


def test_retrieve_keyword_with_no_overlap_returns_empty():
    docs = [Document(id="d1", content="statin therapy cardiovascular disease", source="s")]
    assert retrieve_keyword(set(_tokenize("xyzzy quibble frobnicate")), docs) == []


def test_retrieve_keyword_ranks_stronger_overlap_first():
    weak = Document(id="weak", content="diabetes guideline mentions blood pressure once", source="s")
    strong = Document(id="strong", content="blood pressure blood pressure target adults", source="s")
    hits = retrieve_keyword(set(_tokenize("blood pressure target")), [weak, strong])
    assert hits
    assert hits[0]["id"] == "strong"


def test_retrieve_keyword_result_shape():
    doc = Document(id="d1", content="hypertension blood pressure target adults", source="s")
    hits = retrieve_keyword(set(_tokenize("hypertension blood pressure")), [doc])
    assert hits
    assert set(hits[0].keys()) == {"id", "content", "source", "citation", "url", "score", "metadata"}


def test_fuse_combines_keyword_and_dense_hits():
    keyword_doc = Document(
        id="keyword-match", content="hypertension blood pressure target adults", source="s"
    )
    dense_doc = Document(id="dense-match", content="cardiac output regulation mechanism", source="s")
    keyword_hits = retrieve_keyword(set(_tokenize("blood pressure adults")), [keyword_doc])
    dense_hits = [ScoredDoc(id="dense-match", score=0.9)]
    by_id = {"keyword-match": keyword_doc, "dense-match": dense_doc}

    fused = _fuse(keyword_hits, dense_hits, candidate_pool_size=10, by_id=by_id)
    ids = {r["id"] for r in fused}
    assert "keyword-match" in ids
    assert "dense-match" in ids


def test_scored_doc_is_a_plain_dataclass():
    sd = ScoredDoc(id="x", score=0.5)
    assert sd.id == "x"
    assert sd.score == 0.5


def test_fuse_ignores_a_dense_hit_id_missing_from_by_id():
    """A dense hit for a document that vanished between the pgvector query
    and the keyword-scan pass (e.g. a real concurrent delete) must be
    dropped, not raise."""
    dense_hits = [ScoredDoc(id="ghost", score=0.9)]
    fused = _fuse([], dense_hits, candidate_pool_size=10, by_id={})
    assert fused == []


# --------------------------------------------------------------------------
# Integration — real pgvector-backed retrieve(), against the local
# docker-compose Postgres. Skips automatically when unreachable.
# --------------------------------------------------------------------------

LOCAL_POSTGRES_HOST = "localhost"
LOCAL_POSTGRES_PORT = 5433
LOCAL_POSTGRES_URL = f"postgresql+asyncpg://clinical_ai:clinical_ai_password@{LOCAL_POSTGRES_HOST}:{LOCAL_POSTGRES_PORT}/clinical_ai_db"


def _local_postgres_reachable() -> bool:
    try:
        with socket.create_connection((LOCAL_POSTGRES_HOST, LOCAL_POSTGRES_PORT), timeout=1):
            return True
    except OSError:
        return False


_needs_local_postgres = pytest.mark.skipif(
    not _local_postgres_reachable(),
    reason=(
        f"no Postgres reachable at {LOCAL_POSTGRES_HOST}:{LOCAL_POSTGRES_PORT} — "
        "run `docker compose up -d postgres`"
    ),
)


class _FakeEmbeddingProvider:
    """Maps exact strings to hand-picked 768-dim vectors (padded from a
    short hand-written prefix — `guideline_documents.embedding` is a fixed
    768-dim pgvector column, so a real insert needs the real width);
    anything unmapped raises, mirroring a real provider's behavior for
    out-of-corpus text."""

    model_id = "fake-embedding-model"
    dimension = 768

    def __init__(self, vectors):
        self._vectors = {k: self._pad(v) for k, v in vectors.items()}

    @staticmethod
    def _pad(short_vector):
        return list(short_vector) + [0.0] * (768 - len(short_vector))

    def _lookup(self, text):
        if text not in self._vectors:
            raise EmbeddingUnavailable(f"no fake vector for: {text!r}")
        return self._vectors[text]

    def embed_documents(self, texts):
        return [self._lookup(t) for t in texts]

    def embed_query(self, text):
        return self._lookup(text)

    def add(self, text, short_vector):
        self._vectors[text] = self._pad(short_vector)


@pytest.fixture
def pg_session_factory():
    engine = create_async_engine(LOCAL_POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory


@pytest.fixture
async def cleanup_docs(pg_session_factory):
    """Tracks synthetic document ids a test inserts and deletes them
    afterward, so these tests never leave rows behind in a database that
    also holds the real seeded corpus."""
    from sqlalchemy import delete

    from data.schemas import GuidelineDocument

    ids: list[str] = []
    yield ids
    if ids:
        async with pg_session_factory() as session:
            await session.execute(delete(GuidelineDocument).where(GuidelineDocument.id.in_(ids)))
            await session.commit()


@_needs_local_postgres
async def test_retrieve_ranks_more_relevant_document_first(pg_session_factory):
    """The single most relevant document must still rank first even after
    MMR reranking (Phase 4a, SPEC-005) — MMR trades off pure relevance-order
    for diversity among the *rest* of the results, so scores past the top
    hit are no longer guaranteed strictly descending. Exercised against
    the real seeded corpus."""
    from data.embeddings.cached import CachedEmbeddingProvider

    pipeline = RAGPipeline(
        embedding_provider=CachedEmbeddingProvider(inner=None), session_factory=pg_session_factory
    )
    results = await pipeline.retrieve("A1C goal nonpregnant adults type 2 diabetes", top_k=5)
    assert results
    assert results[0]["id"] == "ada-2024-hba1c"


@_needs_local_postgres
async def test_add_document_is_retrievable(pg_session_factory, cleanup_docs):
    provider = _FakeEmbeddingProvider({})
    pipeline = RAGPipeline(
        embedding_provider=provider, session_factory=pg_session_factory, min_similarity=0.5
    )
    doc = Document(
        id="test-doc-1",
        content="Zebrafish congenital cardiomyopathy screening protocol adults",
        source="Test Source",
        metadata={"organization": "TestOrg", "year": 2025, "title": "Zebrafish Screening"},
    )
    cleanup_docs.append(doc.id)
    await pipeline.add_document(doc)

    results = await pipeline.retrieve("zebrafish congenital cardiomyopathy screening", top_k=1)
    assert results[0]["id"] == "test-doc-1"


@_needs_local_postgres
async def test_medical_knowledge_base_search_delegates_to_pipeline(pg_session_factory):
    from data.embeddings.cached import CachedEmbeddingProvider

    kb = MedicalKnowledgeBase(embedding_provider=CachedEmbeddingProvider(inner=None))
    kb.pipeline._session_factory = pg_session_factory
    results = await kb.search("A1C goal type 2 diabetes", top_k=1)
    assert results
    assert results[0]["id"] == "ada-2024-hba1c"


@_needs_local_postgres
async def test_hybrid_retrieval_finds_paraphrase_with_zero_keyword_overlap(pg_session_factory, cleanup_docs):
    doc = Document(
        id="ear-infection-doc-test", content="Amoxicillin for acute otitis media in children", source="s"
    )
    query = "my kid has an ear infection what antibiotic"
    provider = _FakeEmbeddingProvider({doc.content: [1.0, 0.0], query: [1.0, 0.0]})
    pipeline = RAGPipeline(
        embedding_provider=provider, session_factory=pg_session_factory, min_similarity=0.5
    )
    cleanup_docs.append(doc.id)
    await pipeline.add_document(doc)

    # No shared vocabulary at all -> keyword scoring alone would miss this.
    assert retrieve_keyword(set(_tokenize(query)), [doc]) == []

    results = await pipeline.retrieve(query, top_k=3)
    assert results
    assert results[0]["id"] == "ear-infection-doc-test"


@_needs_local_postgres
async def test_hybrid_retrieval_drops_dense_hits_below_similarity_floor(pg_session_factory, cleanup_docs):
    doc = Document(
        id="unrelated-doc-test", content="Zebrafish congenital cardiomyopathy screening", source="s"
    )
    query = "tax filing advice for small business zzqx"
    provider = _FakeEmbeddingProvider({doc.content: [1.0, 0.0], query: [0.1, 0.995]})
    pipeline = RAGPipeline(
        embedding_provider=provider, session_factory=pg_session_factory, min_similarity=0.5
    )
    cleanup_docs.append(doc.id)
    await pipeline.add_document(doc)

    assert await pipeline.retrieve(query, top_k=3) == []


@_needs_local_postgres
async def test_hybrid_retrieval_falls_back_to_keyword_when_query_embedding_unavailable(
    pg_session_factory, cleanup_docs
):
    doc = Document(
        id="fallback-doc-test", content="statin therapy cardiovascular disease prevention zzqx", source="s"
    )
    provider = _FakeEmbeddingProvider({doc.content: [1.0, 0.0]})  # query text deliberately unmapped
    pipeline = RAGPipeline(
        embedding_provider=provider, session_factory=pg_session_factory, min_similarity=0.5
    )
    cleanup_docs.append(doc.id)
    await pipeline.add_document(doc)

    results = await pipeline.retrieve("statin therapy cardiovascular zzqx", top_k=3)
    assert results
    assert results[0]["id"] == "fallback-doc-test"


@_needs_local_postgres
async def test_hybrid_retrieval_output_shape_matches_keyword_only(pg_session_factory, cleanup_docs):
    doc = Document(id="shape-doc-test", content="statin therapy cardiovascular disease zzqx", source="s")
    provider = _FakeEmbeddingProvider({doc.content: [1.0, 0.0], "statin therapy zzqx": [1.0, 0.0]})
    pipeline = RAGPipeline(
        embedding_provider=provider, session_factory=pg_session_factory, min_similarity=0.5
    )
    cleanup_docs.append(doc.id)
    await pipeline.add_document(doc)

    results = await pipeline.retrieve("statin therapy zzqx", top_k=1)
    assert results
    assert set(results[0].keys()) == {"id", "content", "source", "citation", "url", "score", "metadata"}
