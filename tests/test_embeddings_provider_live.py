"""Tests for `GeminiEmbeddingProvider` (the live provider), mocking
`genai.Client.models.embed_content` directly — mirrors the pattern in
tests/test_gemini_client.py. No network calls."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from data.embeddings.base import EmbeddingUnavailable
from data.embeddings.gemini import GeminiEmbeddingProvider


def _embedding(values):
    return SimpleNamespace(values=values)


def _response(vectors):
    return SimpleNamespace(embeddings=[_embedding(v) for v in vectors])


async def _noop_sleep(_seconds):
    return None


def _sync_noop_sleep(_seconds):
    return None


class _FakeModels:
    def __init__(self, responses=None, raise_once=None):
        self.responses = list(responses or [])
        self.calls = []
        self._raise_once = raise_once

    def embed_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._raise_once is not None:
            exc = self._raise_once
            self._raise_once = None
            raise exc
        return self.responses.pop(0)


def _make_provider(fake_models, **kwargs):
    provider = GeminiEmbeddingProvider(api_key="fake-key", sleep=_sync_noop_sleep, **kwargs)
    provider._client = SimpleNamespace(models=fake_models)
    return provider


def test_no_api_key_raises_unavailable():
    provider = GeminiEmbeddingProvider(api_key=None)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("hello")


def test_embed_documents_normalizes_and_returns_vectors():
    fake = _FakeModels(responses=[_response([[3.0, 4.0], [0.0, 5.0]])])
    provider = _make_provider(fake, dimension=2)

    vectors = provider.embed_documents(["doc one", "doc two"])
    assert vectors[0] == pytest.approx([0.6, 0.8])
    assert vectors[1] == pytest.approx([0.0, 1.0])
    assert fake.calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"


def test_embed_query_uses_retrieval_query_task_type():
    fake = _FakeModels(responses=[_response([[1.0, 0.0]])])
    provider = _make_provider(fake, dimension=2)

    vector = provider.embed_query("what is the goal")
    assert vector == [1.0, 0.0]
    assert fake.calls[0]["config"].task_type == "RETRIEVAL_QUERY"
    assert fake.calls[0]["contents"] == ["what is the goal"]


def test_retries_on_429_then_succeeds():
    exc = errors.ClientError(429, {"error": {"message": "rate limited"}})
    fake = _FakeModels(responses=[_response([[1.0, 0.0]])], raise_once=exc)
    provider = _make_provider(fake, dimension=2, max_retries=2)

    vector = provider.embed_query("hello")
    assert vector == [1.0, 0.0]


def test_persistent_429_raises_unavailable():
    exc = errors.ClientError(429, {"error": {"message": "rate limited"}})

    class _AlwaysFails(_FakeModels):
        def embed_content(self, model, contents, config):
            raise exc

    provider = _make_provider(_AlwaysFails(), dimension=2, max_retries=2)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("hello")


def test_400_does_not_retry():
    exc = errors.ClientError(400, {"error": {"message": "bad request"}})
    calls = {"count": 0}

    class _Fails400(_FakeModels):
        def embed_content(self, model, contents, config):
            calls["count"] += 1
            raise exc

    provider = _make_provider(_Fails400(), dimension=2, max_retries=3)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("hello")
    assert calls["count"] == 1


def test_server_error_retries_then_raises():
    exc = errors.ServerError(503, {"error": {"message": "unavailable"}})

    class _AlwaysFails(_FakeModels):
        def embed_content(self, model, contents, config):
            raise exc

    provider = _make_provider(_AlwaysFails(), dimension=2, max_retries=2)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("hello")
