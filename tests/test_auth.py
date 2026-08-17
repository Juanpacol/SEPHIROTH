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
async def test_registration_defaults_to_clinician_role(client):
    """Proves the User.role server_default: a freshly registered user
    gets role="clinician" without the request ever naming a role."""
    async with client:
        res = await client.post("/api/auth/register", json=CREDS)
        assert res.status_code == 201
        body = res.json()["user"]
        assert body["role"] == "clinician"
        assert body["patient_id"] is None


@pytest.mark.asyncio
async def test_register_rejects_role_and_patient_id_fields(client):
    """RegisterRequest forbids extra fields — a caller must never be able
    to smuggle role/patient_id into a clinician registration."""
    async with client:
        res = await client.post("/api/auth/register", json={**CREDS, "role": "patient"})
        assert res.status_code == 422


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


@pytest.mark.asyncio
async def test_update_profile(client):
    async with client:
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = await client.patch(
            "/api/auth/me",
            json={"email": "newmail@example.org", "name": "Dr. New Name"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json() == {
            "id": res.json()["id"],
            "email": "newmail@example.org",
            "name": "Dr. New Name",
            "role": "clinician",
            "patient_id": None,
        }

        res = await client.get("/api/auth/me", headers=headers)
        assert res.json()["email"] == "newmail@example.org"


@pytest.mark.asyncio
async def test_update_profile_duplicate_email_409(client):
    async with client:
        other = {**CREDS, "email": "other@example.org"}
        await client.post("/api/auth/register", json=other)
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]

        res = await client.patch(
            "/api/auth/me",
            json={"email": other["email"], "name": CREDS["name"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 409


@pytest.mark.asyncio
async def test_change_password_success_then_login(client):
    async with client:
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]

        res = await client.post(
            "/api/auth/change-password",
            json={"current_password": CREDS["password"], "new_password": "newpassword456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 204

        res = await client.post(
            "/api/auth/login", json={"email": CREDS["email"], "password": "newpassword456"}
        )
        assert res.status_code == 200

        res = await client.post(
            "/api/auth/login", json={"email": CREDS["email"], "password": CREDS["password"]}
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_change_password_wrong_current_401(client):
    async with client:
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]

        res = await client.post(
            "/api/auth/change-password",
            json={"current_password": "wrongcurrent", "new_password": "newpassword456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 401
