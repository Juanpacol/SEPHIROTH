"""The default provider, and the embedding space that has to match it.

A clinical product whose no-configuration default ships patient text to a third
party has the wrong default, however good the documentation is. SPEC-022 flips
it: an install that says nothing runs locally and sends nothing.

The embedding half is a real correctness bug rather than a policy choice.
`split` runs chat on Ollama and only vision on Gemini, but embedding selection
keyed on `llm_provider == "ollama"` alone, so a `split` deployment built its
cached artifact with one model and answered cache misses with another. Vectors
from two embedding models are not comparable; the similarity scores were
quietly wrong and nothing failed.

Verifies AC-022-01, AC-022-06 (docs/specs/SPEC-022-local-ai.md).
"""

import pytest

import sephiroth.models.factory as factory_module
from sephiroth.models import GeminiClient
from sephiroth.models.ollama import OllamaClient


def _settings(monkeypatch, **overrides):
    from core.config import Settings

    settings = Settings(_env_file=None, environment="development", **overrides)
    monkeypatch.setattr(factory_module, "settings", settings)
    monkeypatch.setattr(factory_module, "_client", None)
    return settings


class TestDefaultProvider:
    def test_a_configuration_that_says_nothing_runs_locally(self, monkeypatch):
        """AC-022-01 — no provider, no keys, nothing leaves the machine."""
        _settings(monkeypatch)
        client = factory_module.get_llm_client()

        assert isinstance(client, OllamaClient)
        assert client.describe().local is True

    def test_a_stray_gemini_key_does_not_silently_reselect_gemini(self, monkeypatch):
        """The upgrade case: a deployment that had `GEMINI_API_KEY` and never
        set `LLM_PROVIDER` was getting Gemini by omission. Having a key is not
        the same as asking for it to be used."""
        _settings(monkeypatch, gemini_api_key="fake-gemini-key")
        client = factory_module.get_llm_client()

        assert isinstance(client, OllamaClient)

    def test_gemini_is_still_available_when_asked_for(self, monkeypatch):
        _settings(monkeypatch, llm_provider="gemini", gemini_api_key="fake-gemini-key")
        assert isinstance(factory_module.get_llm_client(), GeminiClient)

    def test_the_default_provider_reports_itself_honestly(self, monkeypatch):
        _settings(monkeypatch)
        info = factory_module.get_llm_client().describe()

        assert info.provider == "ollama"
        assert info.local is True
        assert "gemini" not in info.model


class TestEmbeddingSpaceMatchesTheChatProvider:
    """AC-022-06."""

    @pytest.mark.parametrize("provider", ["ollama", "split"])
    def test_a_local_chat_provider_selects_local_embeddings(self, monkeypatch, provider):
        import core.config as config_module
        from core.config import Settings
        from data import embeddings as embeddings_module
        from data.embeddings.ollama import OllamaEmbeddingProvider

        monkeypatch.setattr(
            config_module,
            "settings",
            Settings(_env_file=None, environment="development", llm_provider=provider),
        )

        provider_obj = embeddings_module.get_embedding_provider()

        assert provider_obj is not None
        assert isinstance(provider_obj._inner, OllamaEmbeddingProvider), (
            f"{provider} answers cache misses from a different vector space than its artifact"
        )

    def test_gemini_still_selects_gemini_embeddings(self, monkeypatch):
        import core.config as config_module
        from core.config import Settings
        from data import embeddings as embeddings_module
        from data.embeddings import GeminiEmbeddingProvider

        monkeypatch.setattr(
            config_module,
            "settings",
            Settings(
                _env_file=None,
                environment="development",
                llm_provider="gemini",
                gemini_api_key="fake-gemini-key",
            ),
        )

        assert isinstance(embeddings_module.get_embedding_provider()._inner, GeminiEmbeddingProvider)
