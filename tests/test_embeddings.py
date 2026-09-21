"""Unit tests for the embedding provider layer — cache behavior, hashing
determinism, and the "never silently degrade" contract. No network calls.

The in-memory vector store this file used to also cover
(`data.vectors.InMemoryVectorStore`) was deleted in Phase 15
(SPEC-030/ADR-017) — dense retrieval now queries pgvector directly, see
`tests/test_rag_pipeline.py`/`tests/test_embeddings_matching.py`.
"""

import gzip
import json
import math

import pytest

from data.embeddings.base import EmbeddingUnavailable
from data.embeddings.cached import CachedEmbeddingProvider, _cache_key, load_artifact
from data.embeddings.gemini import _normalize


def test_cache_key_is_deterministic():
    a = _cache_key("model-x", "RETRIEVAL_DOCUMENT", "some text")
    b = _cache_key("model-x", "RETRIEVAL_DOCUMENT", "some text")
    assert a == b


def test_cache_key_differs_by_task_type():
    doc_key = _cache_key("model-x", "RETRIEVAL_DOCUMENT", "some text")
    query_key = _cache_key("model-x", "RETRIEVAL_QUERY", "some text")
    assert doc_key != query_key


def test_cache_key_differs_by_model():
    a = _cache_key("model-a", "RETRIEVAL_DOCUMENT", "some text")
    b = _cache_key("model-b", "RETRIEVAL_DOCUMENT", "some text")
    assert a != b


def test_load_artifact_missing_file_returns_none(tmp_path):
    assert load_artifact(tmp_path / "does-not-exist.json.gz") is None


def test_load_artifact_reads_gzipped_json(tmp_path):
    path = tmp_path / "artifact.json.gz"
    payload = {"model_id": "m", "dimension": 3, "vectors": {}, "corpus_sha256": "abc"}
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)
    loaded = load_artifact(path)
    assert loaded == payload


def test_cached_provider_no_artifact_no_inner_raises_on_miss(tmp_path):
    provider = CachedEmbeddingProvider(inner=None, artifact_path=tmp_path / "missing.json.gz")
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("some clinical question")


def test_cached_provider_hits_cache_without_inner(tmp_path):
    key = _cache_key("test-model", "RETRIEVAL_QUERY", "hello")
    path = tmp_path / "artifact.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump({"model_id": "test-model", "dimension": 2, "vectors": {key: [0.6, 0.8]}}, f)

    provider = CachedEmbeddingProvider(inner=None, artifact_path=path)
    assert provider.embed_query("hello") == [0.6, 0.8]


def test_cached_provider_falls_through_to_inner_on_miss(tmp_path):
    class _FakeInner:
        model_id = "test-model"
        dimension = 2

        def embed_query(self, text):
            return [1.0, 0.0]

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

    provider = CachedEmbeddingProvider(inner=_FakeInner(), artifact_path=tmp_path / "missing.json.gz")
    assert provider.embed_query("anything") == [1.0, 0.0]
    # Second call for the same text is served from the now-populated in-process cache.
    assert provider.embed_query("anything") == [1.0, 0.0]


def test_normalize_produces_unit_vector():
    vec = _normalize([3.0, 4.0])
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-9


def test_normalize_zero_vector_is_safe():
    assert _normalize([0.0, 0.0]) == [0.0, 0.0]
