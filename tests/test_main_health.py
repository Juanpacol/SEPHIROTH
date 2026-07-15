"""Smoke test for the top-level FastAPI app's /health endpoint (no lifespan,
no DB — httpx ASGITransport doesn't invoke lifespan events)."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert "model" in body
