"""Tests for the keyword-scored RAG pipeline over the seeded guideline corpus."""

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
    pipeline = RAGPipeline()
    results = pipeline.retrieve("A1C goal nonpregnant adults type 2 diabetes", top_k=5)
    assert results
    assert results[0]["id"] == "ada-2024-hba1c"
    # scores should be sorted descending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_respects_top_k():
    pipeline = RAGPipeline()
    results = pipeline.retrieve("diabetes guideline recommendation therapy", top_k=2)
    assert len(results) <= 2


def test_retrieve_result_shape():
    pipeline = RAGPipeline()
    results = pipeline.retrieve("hypertension blood pressure target adults", top_k=1)
    assert results
    hit = results[0]
    assert set(hit.keys()) == {"id", "content", "source", "citation", "score", "metadata"}
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
