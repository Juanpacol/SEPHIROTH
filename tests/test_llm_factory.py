"""Tests for get_llm_client()'s composition logic: bare GeminiClient unless
GROQ_API_KEY is configured, in which case it wraps a FallbackLLMClient.

This module patches the factory's module-level `settings`/`_client` globals
directly on `sephiroth.models.factory`, where `get_llm_client()` is defined and
reads them from. Through Phase 2, `intelligence.llm.factory` was a re-export
shim over this module (patching the shim's copy of those bindings would have
silently done nothing — see `docs/specs/SPEC-001-model-provider.md` §10); the
shim was deleted in Phase 3 (DEBT-008).
"""

import sephiroth.models.factory as factory_module
from sephiroth.models import FallbackLLMClient, GeminiClient, GroqClient, OllamaClient, VisionChatSplitClient


def _reload_settings(monkeypatch, **overrides):
    from core.config import Settings

    settings = Settings(_env_file=None, environment="development", **overrides)
    monkeypatch.setattr(factory_module, "settings", settings)
    monkeypatch.setattr(factory_module, "_client", None)
    return settings


def test_returns_bare_gemini_client_without_groq_key(monkeypatch):
    _reload_settings(monkeypatch, gemini_api_key="fake-gemini-key", groq_api_key=None)
    client = factory_module.get_llm_client()
    assert isinstance(client, GeminiClient)


def test_returns_fallback_client_with_groq_key(monkeypatch):
    _reload_settings(monkeypatch, gemini_api_key="fake-gemini-key", groq_api_key="fake-groq-key")
    client = factory_module.get_llm_client()
    assert isinstance(client, FallbackLLMClient)
    assert isinstance(client.primary, GeminiClient)


def test_fallback_disabled_returns_bare_gemini_client(monkeypatch):
    _reload_settings(
        monkeypatch, gemini_api_key="fake-gemini-key", groq_api_key="fake-groq-key", llm_enable_fallback=False
    )
    client = factory_module.get_llm_client()
    assert isinstance(client, GeminiClient)


def test_client_is_cached_across_calls(monkeypatch):
    _reload_settings(monkeypatch, gemini_api_key="fake-gemini-key")
    first = factory_module.get_llm_client()
    second = factory_module.get_llm_client()
    assert first is second


def test_llm_provider_groq_yields_a_bare_groq_primary_client(monkeypatch):
    """AC-001-07: llm_provider='groq' selects Groq as primary — a bare
    GroqClient, not a Gemini-primary client wrapping Groq. No fallback wraps
    it: Groq's own fallback direction is out of scope for this phase (SPEC-001 NG-1)."""
    _reload_settings(monkeypatch, groq_api_key="fake-groq-key", llm_provider="groq")
    client = factory_module.get_llm_client()
    assert isinstance(client, GroqClient)
    assert not isinstance(client, FallbackLLMClient)


def test_llm_provider_split_routes_vision_to_gemini_chat_to_ollama_with_groq_fallback(monkeypatch):
    """AC (runtime audit, vision/chat split): llm_provider='split' sends
    describe_image to a bare GeminiClient and chat/generate_json to a
    FallbackLLMClient(primary=Ollama, secondary=Groq) — the architecture
    decided after comparing providers with the eval harness."""
    _reload_settings(
        monkeypatch,
        gemini_api_key="fake-gemini-key",
        groq_api_key="fake-groq-key",
        ollama_api_key="fake-openrouter-key",
        llm_provider="split",
    )
    client = factory_module.get_llm_client()
    assert isinstance(client, VisionChatSplitClient)
    assert isinstance(client.vision_client, GeminiClient)
    assert isinstance(client.chat_client, FallbackLLMClient)
    assert isinstance(client.chat_client.primary, OllamaClient)
    assert isinstance(client.chat_client.secondary, GroqClient)


def test_llm_provider_split_without_groq_key_has_no_chat_fallback(monkeypatch):
    _reload_settings(
        monkeypatch,
        gemini_api_key="fake-gemini-key",
        groq_api_key=None,
        ollama_api_key="fake-openrouter-key",
        llm_provider="split",
    )
    client = factory_module.get_llm_client()
    assert isinstance(client, VisionChatSplitClient)
    assert isinstance(client.chat_client, OllamaClient)
    assert not isinstance(client.chat_client, FallbackLLMClient)


def test_llm_provider_groq_ignores_gemini_key(monkeypatch):
    """Even with a Gemini key present, llm_provider='groq' must select Groq —
    provider choice is config-driven, not inferred from which keys are set."""
    _reload_settings(
        monkeypatch, gemini_api_key="fake-gemini-key", groq_api_key="fake-groq-key", llm_provider="groq"
    )
    client = factory_module.get_llm_client()
    assert isinstance(client, GroqClient)
