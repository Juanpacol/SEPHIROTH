"""Tests for the keyword-scored RAG pipeline over the seeded guideline corpus."""

from data.embeddings.base import EmbeddingUnavailable
from data.rag import SEED_GUIDELINES, Document, MedicalKnowledgeBase, RAGPipeline, _tokenize


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


def test_retrieve_with_no_overlap_returns_empty():
    pipeline = RAGPipeline()
    assert pipeline.retrieve("xyzzy quibble frobnicate") == []


def test_retrieve_stopword_only_query_returns_empty():
    pipeline = RAGPipeline()
    assert pipeline.retrieve("what is the for") == []


def test_retrieve_ranks_more_relevant_document_first():
    """The single most relevant document must still rank first even after
    MMR reranking (Phase 4a, SPEC-005) — MMR trades off pure relevance-order
    for diversity among the *rest* of the results, so scores past the top
    hit are no longer guaranteed strictly descending."""
    pipeline = RAGPipeline()
    results = pipeline.retrieve("A1C goal nonpregnant adults type 2 diabetes", top_k=5)
    assert results
    assert results[0]["id"] == "ada-2024-hba1c"


def test_retrieve_respects_top_k():
    pipeline = RAGPipeline()
    results = pipeline.retrieve("diabetes guideline recommendation therapy", top_k=2)
    assert len(results) <= 2


def test_retrieve_result_shape():
    pipeline = RAGPipeline()
    results = pipeline.retrieve("hypertension blood pressure target adults", top_k=1)
    assert results
    hit = results[0]
    assert set(hit.keys()) == {"id", "content", "source", "citation", "url", "score", "metadata"}
    assert isinstance(hit["metadata"], dict)


def test_add_document_is_retrievable():
    pipeline = RAGPipeline()
    pipeline.add_document(
        Document(
            id="test-doc-1",
            content="Zebrafish congenital cardiomyopathy screening protocol adults",
            source="Test Source",
            metadata={"organization": "TestOrg", "year": 2025, "title": "Zebrafish Screening"},
        )
    )
    results = pipeline.retrieve("zebrafish congenital cardiomyopathy screening", top_k=1)
    assert results[0]["id"] == "test-doc-1"


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


def test_medical_knowledge_base_search_delegates_to_pipeline():
    kb = MedicalKnowledgeBase()
    results = kb.search("A1C goal type 2 diabetes", top_k=1)
    assert results
    assert results[0]["id"] == "ada-2024-hba1c"


# --- Hybrid (dense + keyword) retrieval, using hand-crafted synthetic ---
# --- vectors so fusion/threshold behavior is testable without a real   ---
# --- embedding model or network access. See tests/test_embeddings_    ---
# --- matching.py for tests against the real committed artifact.       ---


class _FakeEmbeddingProvider:
    """Maps exact strings to hand-picked vectors; anything unmapped raises,
    mirroring a real provider's behavior for out-of-corpus text."""

    model_id = "fake-embedding-model"
    dimension = 2

    def __init__(self, vectors):
        self._vectors = vectors

    def _lookup(self, text):
        if text not in self._vectors:
            raise EmbeddingUnavailable(f"no fake vector for: {text!r}")
        return self._vectors[text]

    def embed_documents(self, texts):
        return [self._lookup(t) for t in texts]

    def embed_query(self, text):
        return self._lookup(text)


def _pipeline_with_docs_and_vectors(docs_and_vectors, min_similarity=0.5):
    """Builds a small pipeline (no seed corpus) wired to a fake provider
    whose vectors are unit-norm so dot product == cosine similarity."""
    docs = [d for d, _ in docs_and_vectors]
    vectors = {d.content: v for d, v in docs_and_vectors}
    pipeline = RAGPipeline(seed=False, min_similarity=min_similarity)
    for doc in docs:
        pipeline.add_document(doc)
    pipeline._embedding_provider = _FakeEmbeddingProvider(vectors)
    pipeline._index_documents(docs)
    return pipeline


def test_hybrid_retrieval_finds_paraphrase_with_zero_keyword_overlap():
    doc = Document(
        id="ear-infection-doc", content="Amoxicillin for acute otitis media in children", source="s"
    )
    query = "my kid has an ear infection what antibiotic"
    pipeline = _pipeline_with_docs_and_vectors([(doc, [1.0, 0.0])])
    # No shared vocabulary at all -> keyword scoring alone would miss this.
    assert pipeline._retrieve_keyword(set(_tokenize(query))) == []

    pipeline._embedding_provider._vectors[query] = [1.0, 0.0]  # perfect semantic match
    results = pipeline.retrieve(query, top_k=3)
    assert results
    assert results[0]["id"] == "ear-infection-doc"


def test_hybrid_retrieval_drops_dense_hits_below_similarity_floor():
    doc = Document(id="unrelated-doc", content="Zebrafish congenital cardiomyopathy screening", source="s")
    query = "tax filing advice for small business"
    pipeline = _pipeline_with_docs_and_vectors([(doc, [1.0, 0.0])], min_similarity=0.5)
    pipeline._embedding_provider._vectors[query] = [0.1, 0.995]  # low cosine similarity (~0.1)

    assert pipeline.retrieve(query, top_k=3) == []


def test_hybrid_retrieval_falls_back_to_keyword_when_embedding_unavailable():
    doc = Document(id="fallback-doc", content="statin therapy cardiovascular disease prevention", source="s")
    pipeline = RAGPipeline(seed=False)
    pipeline.add_document(doc)
    pipeline._embedding_provider = _FakeEmbeddingProvider({})  # every lookup raises

    results = pipeline.retrieve("statin therapy cardiovascular", top_k=3)
    assert results
    assert results[0]["id"] == "fallback-doc"


def test_hybrid_retrieval_fuses_keyword_and_dense_signals():
    keyword_doc = Document(
        id="keyword-match", content="hypertension blood pressure target adults", source="s"
    )
    dense_doc = Document(id="dense-match", content="cardiac output regulation mechanism", source="s")
    query = "blood pressure control in adults"

    pipeline = _pipeline_with_docs_and_vectors(
        [(keyword_doc, [1.0, 0.0]), (dense_doc, [0.0, 1.0])], min_similarity=0.5
    )
    pipeline._embedding_provider._vectors[query] = [0.0, 1.0]  # only matches dense_doc semantically

    ids = [r["id"] for r in pipeline.retrieve(query, top_k=5)]
    # keyword_doc wins on keyword overlap; dense_doc surfaces purely via
    # the embedding signal — both should appear via RRF fusion.
    assert "keyword-match" in ids
    assert "dense-match" in ids


def test_hybrid_retrieval_output_shape_matches_keyword_only():
    doc = Document(id="shape-doc", content="statin therapy cardiovascular disease", source="s")
    pipeline = _pipeline_with_docs_and_vectors([(doc, [1.0, 0.0])])
    pipeline._embedding_provider._vectors["statin therapy"] = [1.0, 0.0]

    results = pipeline.retrieve("statin therapy", top_k=1)
    assert results
    assert set(results[0].keys()) == {"id", "content", "source", "citation", "url", "score", "metadata"}
