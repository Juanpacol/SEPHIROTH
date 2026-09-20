"""Tests for `VisionChatSplitClient.health()`/`vision_health()` (Phase 3,
local-only isolation spec) and `/health`, `/health/ready`'s provider-aware
reporting."""

import pytest
from httpx import ASGITransport, AsyncClient

import api.main as api_main
import api.routers.agents as agents_router
from core.config import Settings
from sephiroth.models.vision_split import VisionChatSplitClient


class _StubClient:
    model = "stub-model"

    def __init__(self, healthy: bool, raises: bool = False):
        self._healthy = healthy
        self._raises = raises

    async def health(self) -> bool:
        if self._raises:
            raise RuntimeError("boom")
        return self._healthy


@pytest.mark.asyncio
async def test_split_health_ignores_vision_client():
    client = VisionChatSplitClient(chat_client=_StubClient(True), vision_client=_StubClient(False))
    assert await client.health() is True
    assert await client.vision_health() is False


@pytest.mark.asyncio
async def test_split_vision_health_swallows_exceptions():
    vision_client = _StubClient(True, raises=True)
    client = VisionChatSplitClient(chat_client=_StubClient(True), vision_client=vision_client)
    assert await client.vision_health() is False


@pytest.mark.asyncio
async def test_health_endpoint_reports_provider_and_local_only(monkeypatch):
    settings = Settings(_env_file=None, environment="development", llm_provider="ollama")
    monkeypatch.setattr(api_main, "settings", settings)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        body = res.json()
        assert body["model"] == settings.ollama_model
        assert body["provider"] == "ollama"
        assert body["local_only"] is True
        assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_ready_llm_configured_for_local_provider_without_gemini_key(monkeypatch):
    settings = Settings(_env_file=None, environment="development", llm_provider="ollama", gemini_api_key=None)
    monkeypatch.setattr(api_main, "settings", settings)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health/ready")
        body = res.json()
        assert body["checks"]["llm"] == "configured"
        assert body["checks"]["llm_provider"] == "ollama"


@pytest.mark.asyncio
async def test_health_ready_llm_unconfigured_for_gemini_without_key(monkeypatch):
    settings = Settings(_env_file=None, environment="development", llm_provider="gemini", gemini_api_key=None)
    monkeypatch.setattr(api_main, "settings", settings)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health/ready")
        body = res.json()
        assert body["checks"]["llm"] == "unconfigured"
        assert body["checks"]["llm_provider"] == "gemini"


@pytest.mark.asyncio
async def test_health_ready_status_code_ignores_llm_check(monkeypatch):
    """checks["llm"] must never affect the 503 — scripts/smoke_test.sh
    asserts the status code. `checks["database"]` alone decides `ok`, for
    both a configured and an unconfigured LLM."""
    for llm_provider, gemini_api_key in (("gemini", None), ("ollama", None)):
        settings = Settings(
            _env_file=None,
            environment="development",
            llm_provider=llm_provider,
            gemini_api_key=gemini_api_key,
        )
        monkeypatch.setattr(api_main, "settings", settings)

        transport = ASGITransport(app=api_main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/health/ready")
            body = res.json()
            expected_status = 200 if body["checks"]["database"] == "ok" else 503
            assert res.status_code == expected_status


@pytest.mark.asyncio
async def test_consult_not_503_when_only_vision_is_down(monkeypatch):
    """`POST /api/agents/consult` does not return 503 when the chat client
    is healthy and the vision client is not — `_ensure_llm()` only calls
    `get_llm_client().health()`, which for a split client is chat-only."""
    split_stub = VisionChatSplitClient(chat_client=_StubClient(True), vision_client=_StubClient(False))
    monkeypatch.setattr(agents_router, "get_llm_client", lambda: split_stub)

    # Should not raise.
    await agents_router._ensure_llm()
