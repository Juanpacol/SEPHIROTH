"""Account lifecycle: deactivation, password reset, and TOTP MFA."""

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _register(client, email="user@lifecycle.org", password="password123") -> dict:
    res = await client.post("/api/auth/register", json={"email": email, "name": "U", "password": password})
    assert res.status_code == 201
    return res.json()


def _headers(body: dict) -> dict:
    return {"Authorization": f"Bearer {body['access_token']}"}


# --- Deactivation -----------------------------------------------------


async def test_deactivate_blocks_login_and_existing_token(client):
    async with client:
        auth = await _register(client)
        headers = _headers(auth)

        res = await client.post(
            "/api/auth/account/deactivate", json={"password": "password123"}, headers=headers
        )
        assert res.status_code == 204

        # existing token now rejected
        me_res = await client.get("/api/auth/me", headers=headers)
        assert me_res.status_code == 401

        # fresh login also rejected
        login_res = await client.post(
            "/api/auth/login", json={"email": "user@lifecycle.org", "password": "password123"}
        )
        assert login_res.status_code == 401


async def test_deactivate_requires_correct_password(client):
    async with client:
        auth = await _register(client, email="u2@lifecycle.org")
        headers = _headers(auth)
        res = await client.post("/api/auth/account/deactivate", json={"password": "wrong"}, headers=headers)
        assert res.status_code == 401


# --- Password reset -----------------------------------------------------


async def test_password_reset_happy_path(client):
    async with client:
        await _register(client, email="reset@lifecycle.org")

        req = await client.post("/api/auth/password-reset/request", json={"email": "reset@lifecycle.org"})
        assert req.status_code == 202
        token = req.json()["reset_token"]
        assert token

        confirm = await client.post(
            "/api/auth/password-reset/confirm", json={"token": token, "new_password": "newpassword456"}
        )
        assert confirm.status_code == 204

        old_login = await client.post(
            "/api/auth/login", json={"email": "reset@lifecycle.org", "password": "password123"}
        )
        assert old_login.status_code == 401

        new_login = await client.post(
            "/api/auth/login", json={"email": "reset@lifecycle.org", "password": "newpassword456"}
        )
        assert new_login.status_code == 200


async def test_password_reset_unknown_email_still_202_no_token(client):
    async with client:
        res = await client.post("/api/auth/password-reset/request", json={"email": "nobody@lifecycle.org"})
        assert res.status_code == 202
        assert res.json()["reset_token"] is None


async def test_password_reset_token_cannot_be_replayed(client):
    async with client:
        await _register(client, email="replay@lifecycle.org")
        token = (
            await client.post("/api/auth/password-reset/request", json={"email": "replay@lifecycle.org"})
        ).json()["reset_token"]

        first = await client.post(
            "/api/auth/password-reset/confirm", json={"token": token, "new_password": "newpassword456"}
        )
        assert first.status_code == 204

        second = await client.post(
            "/api/auth/password-reset/confirm", json={"token": token, "new_password": "anotherpassword789"}
        )
        assert second.status_code == 400


async def test_password_reset_expired_token_rejected(client, db_session):
    from datetime import datetime, timedelta, timezone

    from data.schemas import PasswordResetToken

    async with client:
        await _register(client, email="expired@lifecycle.org")
        token = (
            await client.post("/api/auth/password-reset/request", json={"email": "expired@lifecycle.org"})
        ).json()["reset_token"]
        token_id = token.split(".")[0]

        reset = await db_session.get(PasswordResetToken, token_id)
        reset.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        await db_session.commit()

        res = await client.post(
            "/api/auth/password-reset/confirm", json={"token": token, "new_password": "newpassword456"}
        )
        assert res.status_code == 400


async def test_password_reset_wrong_token_rejected(client):
    async with client:
        res = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": "does-not-exist.secret", "new_password": "newpassword456"},
        )
        assert res.status_code == 400


# --- MFA (TOTP) -----------------------------------------------------


async def test_mfa_enroll_verify_login_flow(client):
    async with client:
        auth = await _register(client, email="mfa@lifecycle.org")
        headers = _headers(auth)

        enroll = await client.post("/api/auth/mfa/enroll", headers=headers)
        assert enroll.status_code == 200
        secret = enroll.json()["secret"]
        assert enroll.json()["provisioning_uri"].startswith("otpauth://")

        code = pyotp.TOTP(secret).now()
        verify = await client.post("/api/auth/mfa/verify", json={"code": code}, headers=headers)
        assert verify.status_code == 200
        recovery_codes = verify.json()["recovery_codes"]
        assert len(recovery_codes) == 10

        # subsequent login is gated
        login = await client.post(
            "/api/auth/login", json={"email": "mfa@lifecycle.org", "password": "password123"}
        )
        assert login.status_code == 200
        assert login.json()["mfa_required"] is True
        mfa_token = login.json()["mfa_token"]
        assert login.json()["access_token"] is None

        finish = await client.post(
            "/api/auth/login/mfa", json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()}
        )
        assert finish.status_code == 200
        assert finish.json()["access_token"]


async def test_mfa_login_with_recovery_code(client):
    async with client:
        auth = await _register(client, email="mfarec@lifecycle.org")
        headers = _headers(auth)
        secret = (await client.post("/api/auth/mfa/enroll", headers=headers)).json()["secret"]
        recovery_codes = (
            await client.post(
                "/api/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}, headers=headers
            )
        ).json()["recovery_codes"]

        login = await client.post(
            "/api/auth/login", json={"email": "mfarec@lifecycle.org", "password": "password123"}
        )
        mfa_token = login.json()["mfa_token"]

        finish = await client.post(
            "/api/auth/login/mfa", json={"mfa_token": mfa_token, "code": recovery_codes[0]}
        )
        assert finish.status_code == 200

        # single-use: replaying the same recovery code fails
        login2 = await client.post(
            "/api/auth/login", json={"email": "mfarec@lifecycle.org", "password": "password123"}
        )
        mfa_token2 = login2.json()["mfa_token"]
        replay = await client.post(
            "/api/auth/login/mfa", json={"mfa_token": mfa_token2, "code": recovery_codes[0]}
        )
        assert replay.status_code == 401


async def test_mfa_disable(client):
    async with client:
        auth = await _register(client, email="mfadis@lifecycle.org")
        headers = _headers(auth)
        secret = (await client.post("/api/auth/mfa/enroll", headers=headers)).json()["secret"]
        await client.post("/api/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

        disable = await client.post(
            "/api/auth/mfa/disable",
            json={"password": "password123", "code": pyotp.TOTP(secret).now()},
            headers=headers,
        )
        assert disable.status_code == 204

        login = await client.post(
            "/api/auth/login", json={"email": "mfadis@lifecycle.org", "password": "password123"}
        )
        assert login.status_code == 200
        assert login.json()["mfa_required"] is False
        assert login.json()["access_token"]


async def test_mfa_verify_rejects_wrong_code(client):
    async with client:
        auth = await _register(client, email="mfawrong@lifecycle.org")
        headers = _headers(auth)
        await client.post("/api/auth/mfa/enroll", headers=headers)
        res = await client.post("/api/auth/mfa/verify", json={"code": "000000"}, headers=headers)
        assert res.status_code == 400
