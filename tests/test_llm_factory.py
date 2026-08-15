"""Tests for get_llm_client()'s composition logic: bare GeminiClient unless
GROQ_API_KEY is configured, in which case it wraps a FallbackLLMClient."""

import intelligence.llm.factory as factory_module
from intelligence.llm.fallback_client import FallbackLLMClient
from intelligence.llm.gemini_client import GeminiClient


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
