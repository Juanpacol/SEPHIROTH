"""Auth flow tests against an isolated SQLite database."""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from auth import router as auth_router_module
from auth.deps import get_current_user
from core.db import get_session
from data.schemas import User


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/auth")

    @app.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        return {"email": user.email}

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


CREDS = {"email": "doc@example.org", "name": "Dr. Test", "password": "password123"}


@pytest.mark.asyncio
async def test_register_login_me_roundtrip(client):
    async with client:
        res = await client.post("/api/auth/register", json=CREDS)
        assert res.status_code == 201
        token = res.json()["access_token"]

        res = await client.post(
            "/api/auth/login", json={"email": CREDS["email"], "password": CREDS["password"]}
        )
        assert res.status_code == 200

        res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == CREDS["email"]


@pytest.mark.asyncio
async def test_duplicate_email_409(client):
    async with client:
        assert (await client.post("/api/auth/register", json=CREDS)).status_code == 201
        assert (await client.post("/api/auth/register", json=CREDS)).status_code == 409


@pytest.mark.asyncio
async def test_wrong_password_401(client):
    async with client:
        await client.post("/api/auth/register", json=CREDS)
        res = await client.post(
            "/api/auth/login", json={"email": CREDS["email"], "password": "wrongpassword"}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    async with client:
        assert (await client.get("/protected")).status_code == 401
        res = await client.get("/protected", headers={"Authorization": "Bearer garbage"})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_short_password_rejected(client):
    async with client:
        res = await client.post("/api/auth/register", json={**CREDS, "password": "short"})
        assert res.status_code == 422
