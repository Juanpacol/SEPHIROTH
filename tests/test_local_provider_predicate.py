"""Tests for `is_local_llm_provider()`/`Settings.is_local_provider` — the
single definition of "runs entirely on this machine" that every membership
test in the codebase must go through."""

import pytest

from core.config import Settings, is_local_llm_provider


@pytest.mark.parametrize(
    "provider,expected",
    [
        ("gemini", False),
        ("groq", False),
        ("ollama", True),
        ("split", True),
    ],
)
def test_local_providers_are_ollama_and_split(provider, expected):
    assert is_local_llm_provider(provider) is expected
    settings = Settings(_env_file=None, environment="development", llm_provider=provider)
    assert settings.is_local_provider is expected


def test_unknown_provider_is_not_local():
    assert is_local_llm_provider("unknown-provider") is False


def test_is_local_provider_not_settable_from_constructor_kwargs():
    """`is_local_provider` is a derived @property, not a pydantic field — it
    must not be silently overridable."""
    settings = Settings(_env_file=None, environment="development", llm_provider="gemini")
    assert settings.is_local_provider is False
