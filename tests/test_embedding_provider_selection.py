"""Tests for `get_embedding_provider()`'s artifact-driven `inner` selection
(Decision D4, local-only isolation spec) and `GeminiEmbeddingProvider`'s HTTP
timeout. There was no existing test for `get_embedding_provider()` before
this file.

Pattern: build a `Settings(_env_file=None, environment="development",
**overrides)` and `monkeypatch.setattr(core.config, "settings", s)` — note
`data/embeddings/__init__.py` imports `settings` *inside* the function from
`core.config`, so patching the module attribute (not a local binding) is
what takes effect. `DEFAULT_ARTIFACT_PATH` is patched on `data.embeddings`
(the binding `get_embedding_provider()` actually reads) and passed through
explicitly to `CachedEmbeddingProvider`, so the artifact-loading path used
by the test matches what the function under test resolves.
"""

import gzip
import json

import pytest

import core.config
import data.embeddings as embeddings_module
from data.embeddings.gemini import GeminiEmbeddingProvider
from data.embeddings.ollama import OllamaEmbeddingProvider


def _settings(monkeypatch, **overrides):
    settings = core.config.Settings(_env_file=None, environment="development", **overrides)
    monkeypatch.setattr(core.config, "settings", settings)
    return settings


def _write_artifact(tmp_path, model_id: str, dimension: int = 768):
    path = tmp_path / "artifact.json.gz"
    payload = {"model_id": model_id, "dimension": dimension, "vectors": {}}
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)
    return path


# --- GeminiEmbeddingProvider timeout -----------------------------------------


def test_gemini_embedding_provider_sets_http_timeout(monkeypatch):
    recorded = {}

    class _FakeClient:
        def __init__(self, api_key, http_options):
            recorded["api_key"] = api_key
            recorded["timeout"] = http_options.timeout

    monkeypatch.setattr("data.embeddings.gemini.genai.Client", _FakeClient)

    GeminiEmbeddingProvider(api_key="k")
    assert recorded["timeout"] == 60000

    GeminiEmbeddingProvider(api_key="k", timeout_seconds=5)
    assert recorded["timeout"] == 5000


def test_gemini_embedding_provider_without_key_has_no_client():
    from data.embeddings.base import EmbeddingUnavailable

    provider = GeminiEmbeddingProvider(api_key=None)
    assert provider._client is None
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_query("hello")


# --- get_embedding_provider() artifact-driven selection ----------------------


def test_no_artifact_falls_back_to_provider_keyed_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", tmp_path / "does-not-exist.json.gz")

    _settings(monkeypatch, llm_provider="ollama")
    provider = embeddings_module.get_embedding_provider()
    assert isinstance(provider._inner, OllamaEmbeddingProvider)

    _settings(monkeypatch, llm_provider="gemini", gemini_api_key="fake-key")
    provider = embeddings_module.get_embedding_provider()
    assert isinstance(provider._inner, GeminiEmbeddingProvider)


def test_committed_artifact_with_gemini_provider_uses_ollama_inner(monkeypatch, tmp_path):
    """With the real committed artifact (nomic-embed-text) and
    llm_provider="gemini", the live provider must be OllamaEmbeddingProvider
    — never GeminiEmbeddingProvider — because vectors from two embedding
    models are not comparable."""
    path = _write_artifact(tmp_path, "nomic-embed-text")
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", path)
    _settings(monkeypatch, llm_provider="gemini", gemini_api_key="fake-key")

    provider = embeddings_module.get_embedding_provider()
    assert isinstance(provider._inner, OllamaEmbeddingProvider)
    assert provider._inner.model_id == "nomic-embed-text"


@pytest.mark.parametrize("provider_name", ["ollama", "split"])
def test_artifact_with_local_provider_uses_ollama_inner(monkeypatch, tmp_path, provider_name):
    path = _write_artifact(tmp_path, "nomic-embed-text")
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", path)
    _settings(monkeypatch, llm_provider=provider_name)

    provider = embeddings_module.get_embedding_provider()
    assert isinstance(provider._inner, OllamaEmbeddingProvider)
    assert provider._inner.model_id == "nomic-embed-text"
    assert provider._inner._base_url == core.config.settings.ollama_base_url.rstrip("/")


def test_gemini_artifact_with_local_provider_is_cache_only(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path, "gemini-embedding-001")
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", path)
    _settings(monkeypatch, llm_provider="ollama", gemini_api_key="fake-key")

    provider = embeddings_module.get_embedding_provider()
    assert provider._inner is None


def test_gemini_artifact_with_gemini_provider_uses_gemini_inner(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path, "gemini-embedding-001")
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", path)
    _settings(monkeypatch, llm_provider="gemini", gemini_api_key="fake-key")

    provider = embeddings_module.get_embedding_provider()
    assert isinstance(provider._inner, GeminiEmbeddingProvider)
    assert provider._inner.model_id == "gemini-embedding-001"


def test_enable_rag_embeddings_false_returns_none_for_every_provider(monkeypatch, tmp_path):
    path = _write_artifact(tmp_path, "nomic-embed-text")
    monkeypatch.setattr(embeddings_module, "DEFAULT_ARTIFACT_PATH", path)
    for provider_name in ("gemini", "groq", "ollama", "split"):
        _settings(monkeypatch, llm_provider=provider_name, enable_rag_embeddings=False)
        assert embeddings_module.get_embedding_provider() is None


def test_retrieval_min_similarity_pinned():
    assert core.config.settings.retrieval_min_similarity == 0.636
