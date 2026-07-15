"""Tests for /api/medical/* — direct MCP tool endpoints, offline paths."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import medical as medical_router_module


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(medical_router_module.router, prefix="/api/medical")
    return app


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_extract_entities(client):
    async with client:
        res = await client.post(
            "/api/medical/nlp/extract", json={"text": "Patient with diabetes on metformin."}
        )
        assert res.status_code == 200
        assert res.json()["entities"]


@pytest.mark.asyncio
async def test_summarize_note(client):
    async with client:
        res = await client.post(
            "/api/medical/nlp/summarize",
            json={"text": "Patient has diabetes. The weather was nice."},
        )
        assert res.status_code == 200
        assert "summary" in res.json()


@pytest.mark.asyncio
async def test_analyze_image_no_weights(client, tmp_path):
    img_path = tmp_path / "x.png"
    img_path.write_bytes(b"fake")
    async with client:
        res = await client.post(
            "/api/medical/imaging/analyze",
            json={"image_path": str(img_path), "modality": "xray"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "model_not_configured"


@pytest.mark.asyncio
async def test_check_drug_interactions(client):
    async with client:
        res = await client.post("/api/medical/drugs/check", json={"medications": ["warfarin", "aspirin"]})
        assert res.status_code == 200
        assert res.json()["interactions_found"] == 1


@pytest.mark.asyncio
async def test_preview_image_rejects_non_image_extension(client):
    async with client:
        res = await client.get("/api/medical/imaging/preview", params={"path": "/etc/passwd"})
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_preview_image_404_when_missing(client):
    async with client:
        res = await client.get("/api/medical/imaging/preview", params={"path": "/tmp/does-not-exist-xyz.png"})
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_preview_image_serves_existing_file(client, tmp_path):
    img_path = tmp_path / "preview.png"
    img_path.write_bytes(b"fake png bytes")
    async with client:
        res = await client.get("/api/medical/imaging/preview", params={"path": str(img_path)})
        assert res.status_code == 200
