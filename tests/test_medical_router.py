"""Tests for /api/medical/* — direct MCP tool endpoints, offline paths.

Every endpoint requires authentication as of Phase 2
(`docs/specs/SPEC-002-tool-runtime.md`, DEBT-004) — these call tools directly
with attacker-controlled arguments. The `app`/`client` fixtures mirror the
auth-capable pattern from `tests/test_api_agents.py`: mount the auth router,
override `get_session` with the isolated `db_session`, register once, and
reuse the token.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import medical as medical_router_module
from auth import router as auth_router_module
from core.db import get_session

CREDS = {"email": "medical-router@example.org", "name": "Dr. Router", "password": "password123"}


@pytest.fixture
def app(db_session):
    application = FastAPI()
    application.include_router(auth_router_module.router, prefix="/api/auth")
    application.include_router(medical_router_module.router, prefix="/api/medical")

    async def override_session():
        yield db_session

    application.dependency_overrides[get_session] = override_session
    return application


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _auth_headers(client: AsyncClient) -> dict:
    res = await client.post("/api/auth/register", json=CREDS)
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_extract_entities(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/nlp/extract",
            json={"text": "Patient with diabetes on metformin."},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["entities"]


@pytest.mark.asyncio
async def test_extract_entities_requires_auth(client):
    # AC-002-03 (docs/specs/SPEC-002-tool-runtime.md)
    async with client:
        res = await client.post(
            "/api/medical/nlp/extract", json={"text": "Patient with diabetes on metformin."}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_summarize_note(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/nlp/summarize",
            json={"text": "Patient has diabetes. The weather was nice."},
            headers=headers,
        )
        assert res.status_code == 200
        assert "summary" in res.json()


@pytest.mark.asyncio
async def test_analyze_image_no_weights(client, tmp_path):
    img_path = tmp_path / "x.png"
    img_path.write_bytes(b"fake")
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/imaging/analyze",
            json={"image_path": str(img_path), "modality": "xray"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "model_not_configured"


@pytest.mark.asyncio
async def test_check_drug_interactions(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/drugs/check",
            json={"medications": ["warfarin", "aspirin"]},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["interactions_found"] == 1


@pytest.mark.asyncio
async def test_drug_interactions_requires_auth(client):
    async with client:
        res = await client.post("/api/medical/drugs/check", json={"medications": ["warfarin", "aspirin"]})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_upload_image_then_preview_round_trip(client):
    async with client:
        headers = await _auth_headers(client)
        upload_res = await client.post(
            "/api/medical/imaging/upload",
            files={"file": ("scan.png", b"fake png bytes", "image/png")},
            headers=headers,
        )
        assert upload_res.status_code == 200, upload_res.text
        path = upload_res.json()["path"]
        assert path.endswith(".png")

        preview_res = await client.get("/api/medical/imaging/preview", params={"path": path}, headers=headers)
        assert preview_res.status_code == 200
        assert preview_res.content == b"fake png bytes"


@pytest.mark.asyncio
async def test_upload_image_rejects_unsupported_extension(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/imaging/upload",
            files={"file": ("scan.dcm", b"not really dicom", "application/dicom")},
            headers=headers,
        )
        assert res.status_code == 415


@pytest.mark.asyncio
async def test_upload_image_rejects_oversized_file(client, monkeypatch):
    from api.routers import medical as medical_module

    monkeypatch.setattr(medical_module, "_MAX_UPLOAD_BYTES", 10)
    async with client:
        headers = await _auth_headers(client)
        res = await client.post(
            "/api/medical/imaging/upload",
            files={"file": ("scan.png", b"this is definitely more than ten bytes", "image/png")},
            headers=headers,
        )
        assert res.status_code == 413


@pytest.mark.asyncio
async def test_upload_image_requires_auth(client):
    async with client:
        res = await client.post(
            "/api/medical/imaging/upload", files={"file": ("scan.png", b"bytes", "image/png")}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_preview_image_rejects_non_image_extension(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get(
            "/api/medical/imaging/preview", params={"path": "/etc/passwd"}, headers=headers
        )
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_preview_image_404_when_missing(client):
    async with client:
        headers = await _auth_headers(client)
        res = await client.get(
            "/api/medical/imaging/preview",
            params={"path": "/tmp/does-not-exist-xyz.png"},
            headers=headers,
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_preview_image_serves_existing_file(client, tmp_path):
    img_path = tmp_path / "preview.png"
    img_path.write_bytes(b"fake png bytes")
    async with client:
        headers = await _auth_headers(client)
        res = await client.get(
            "/api/medical/imaging/preview", params={"path": str(img_path)}, headers=headers
        )
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_preview_image_requires_auth(client, tmp_path):
    img_path = tmp_path / "preview.png"
    img_path.write_bytes(b"fake png bytes")
    async with client:
        res = await client.get("/api/medical/imaging/preview", params={"path": str(img_path)})
        assert res.status_code == 401
