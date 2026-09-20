"""A local-only run (`llm_provider` in `LOCAL_LLM_PROVIDERS`) must make no
live Google Gemini call of any kind. Every case here sets `gemini_api_key`
to a non-empty value on purpose — the guarantee must hold from
configuration, not from the absence of a key.

This is the single test module that would have caught the original bug: a
run configured for `ollama`/`split` still constructing a `GeminiClient` (for
chat, vision, or embeddings) whenever `GEMINI_API_KEY` happened to be set.
"""

from __future__ import annotations

import io
from typing import Any, List

import pytest
from PIL import Image

import core.config
import data.embeddings.gemini as embeddings_gemini_module
import intelligence.mcp.vision_server as vision_server
import sephiroth.models.factory as factory_module
import sephiroth.models.gemini as gemini_module
from data.embeddings import get_embedding_provider
from data.embeddings.ollama import OllamaEmbeddingProvider
from sephiroth.models import GeminiClient, OllamaClient, get_llm_client, reset_llm_client


def _local_settings(monkeypatch, provider: str, **overrides):
    """Build a `Settings` configured for a local provider *with a Gemini key
    set anyway*, and patch it onto every binding a leak point could read it
    from."""
    settings = core.config.Settings(
        _env_file=None,
        environment="development",
        llm_provider=provider,
        gemini_api_key="fake-gemini-key",
        **overrides,
    )
    monkeypatch.setattr(factory_module, "settings", settings)
    monkeypatch.setattr(core.config, "settings", settings)
    monkeypatch.setattr(factory_module, "_client", None)
    return settings


def _walk_clients(client: Any) -> List[Any]:
    """Yield `client` plus every object reachable via `chat_client`,
    `vision_client`, `primary`, `secondary`, recursively — so the assertion
    holds for any future composition."""
    seen: List[Any] = []
    stack = [client]
    while stack:
        current = stack.pop()
        if current is None or current in seen:
            continue
        seen.append(current)
        for attr in ("chat_client", "vision_client", "primary", "secondary"):
            child = getattr(current, attr, None)
            if child is not None:
                stack.append(child)
    return seen


def _poison_gemini_client(monkeypatch) -> None:
    """The strongest form of the guarantee: fails at *construction*, not
    only at call time. Not applied to the counterweight test, which
    deliberately constructs a real Gemini client."""

    def _poisoned(*args, **kwargs):
        raise AssertionError("a local-only run constructed a live Gemini client")

    monkeypatch.setattr(gemini_module.genai, "Client", _poisoned)
    monkeypatch.setattr(embeddings_gemini_module.genai, "Client", _poisoned)


@pytest.fixture(autouse=True)
def poison_gemini_client(monkeypatch, request):
    """Applies to every test in this module except the counterweight,
    which is parametrized/named separately below and constructs its own
    (unpoisoned) settings/monkeypatch instead of using `_local_settings`."""
    if request.function is test_gemini_provider_still_constructs_a_gemini_client:
        yield
        return
    _poison_gemini_client(monkeypatch)
    yield


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    reset_llm_client()
    yield
    reset_llm_client()


@pytest.mark.parametrize("provider", ["ollama", "split"])
def test_factory_constructs_no_gemini_client(monkeypatch, provider):
    _local_settings(monkeypatch, provider, ollama_vision_model="qwen2.5vl:7b")
    client = get_llm_client()
    assert not any(isinstance(c, GeminiClient) for c in _walk_clients(client))


@pytest.mark.parametrize("provider", ["ollama", "split"])
def test_embedding_provider_is_never_gemini(monkeypatch, provider):
    _local_settings(monkeypatch, provider)
    provider_obj = get_embedding_provider()
    inner = provider_obj._inner
    assert inner is None or isinstance(inner, OllamaEmbeddingProvider)


@pytest.mark.parametrize("provider", ["ollama", "split"])
@pytest.mark.asyncio
async def test_vision_calls_stay_local(monkeypatch, provider):
    settings = _local_settings(monkeypatch, provider, ollama_vision_model="qwen2.5vl:7b")
    client = get_llm_client()

    recorded_urls: List[str] = []

    vision_client = client.vision_client if hasattr(client, "vision_client") else client

    async def _fake_post(url, **kwargs):
        recorded_urls.append(str(url))

        class _Resp:
            status_code = 200

            def json(self):
                return {"message": {"content": "a description"}}

        return _Resp()

    monkeypatch.setattr(vision_client._client, "post", _fake_post)

    fake_image = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(fake_image, format="PNG")
    await client.describe_image(image_bytes=fake_image.getvalue(), mime_type="image/png", prompt="describe")

    assert recorded_urls, "no HTTP call was recorded"
    for url in recorded_urls:
        assert "generativelanguage.googleapis.com" not in url
        assert settings.ollama_base_url.split("://")[1].split("/")[0].split(":")[0] in url


@pytest.mark.parametrize("provider", ["ollama", "split"])
@pytest.mark.asyncio
async def test_health_probes_only_the_local_stack(monkeypatch, provider):
    _local_settings(monkeypatch, provider, ollama_vision_model="qwen2.5vl:7b")
    client = get_llm_client()

    async def _fake_health(self):
        return True

    monkeypatch.setattr(OllamaClient, "health", _fake_health)
    assert await client.health() is True


@pytest.mark.parametrize("provider", ["ollama", "split"])
def test_reported_vision_model_matches_the_client_that_serves_it(monkeypatch, provider):
    settings = _local_settings(monkeypatch, provider, ollama_vision_model="qwen2.5vl:7b")
    client = get_llm_client()

    effective = client.vision_client.vision_model if provider == "split" else client.vision_model
    assert vision_server._active_vision_model_name(settings) == effective


@pytest.mark.asyncio
async def test_split_vision_without_vision_model_raises_llm_unavailable(monkeypatch):
    """No `ollama_vision_model` configured means no live call anywhere —
    `describe_image` must fail closed with `LLMUnavailableError`, not fall
    back to Gemini and not make any HTTP request at all."""
    from sephiroth.models.base import LLMUnavailableError

    _local_settings(monkeypatch, "split")  # ollama_vision_model left unset
    client = get_llm_client()

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("no HTTP call should be made when no vision model is configured")

    monkeypatch.setattr(client.vision_client._client, "post", _fail_if_called)

    fake_image = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(fake_image, format="PNG")
    with pytest.raises(LLMUnavailableError):
        await client.describe_image(
            image_bytes=fake_image.getvalue(), mime_type="image/png", prompt="describe"
        )


def test_split_describe_reports_local(monkeypatch):
    """`describe()` is what `phi_egress_allowed()`-style callers key off of —
    it must report `split` as local, since neither of its two clients ever
    leaves the machine."""
    _local_settings(monkeypatch, "split", ollama_vision_model="qwen2.5vl:7b")
    client = get_llm_client()

    info = client.describe()
    assert info.provider == "split"
    assert info.local is True


def test_gemini_provider_still_constructs_a_gemini_client(monkeypatch):
    """The counterweight: with llm_provider='gemini' and a key,
    get_llm_client() is a GeminiClient. Proves the guard is provider-scoped
    and production is untouched."""
    settings = core.config.Settings(
        _env_file=None, environment="development", llm_provider="gemini", gemini_api_key="fake-gemini-key"
    )
    monkeypatch.setattr(factory_module, "settings", settings)
    monkeypatch.setattr(core.config, "settings", settings)
    monkeypatch.setattr(factory_module, "_client", None)

    client = get_llm_client()
    assert isinstance(client, GeminiClient)
