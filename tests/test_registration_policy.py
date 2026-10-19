"""Who can create a clinician account, by environment (AB#22, ADR-021)."""

from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.config import Settings, settings
from core.db import get_session
from data.schemas import Patient, User

REPO = Path(__file__).resolve().parents[1]
STRONG = {"jwt_secret": "j" * 40}


def _settings(environment, **extra):
    return Settings(
        environment=environment, phi_encryption_key=Fernet.generate_key().decode(), **STRONG, **extra
    )


# --- the default follows the environment ------------------------------------


@pytest.mark.parametrize(
    "environment,expected", [("development", True), ("test", True), ("staging", False), ("production", False)]
)
def test_open_registration_defaults_to_development_and_test_only(environment, expected):
    assert _settings(environment).allow_bootstrap_registration is expected


@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
def test_an_explicit_value_wins_in_every_environment(environment):
    assert _settings(environment, allow_bootstrap_registration=True).allow_bootstrap_registration is True
    assert _settings(environment, allow_bootstrap_registration=False).allow_bootstrap_registration is False


def test_the_environment_variable_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("ALLOW_BOOTSTRAP_REGISTRATION", "true")
    assert _settings("production").allow_bootstrap_registration is True

    monkeypatch.setenv("ALLOW_BOOTSTRAP_REGISTRATION", "false")
    assert _settings("development").allow_bootstrap_registration is False


def test_a_missing_variable_in_production_leaves_registration_closed(monkeypatch):
    # The case the old default got wrong: the variable is simply not there.
    monkeypatch.delenv("ALLOW_BOOTSTRAP_REGISTRATION", raising=False)

    assert _settings("production").allow_bootstrap_registration is False


def test_the_value_is_always_resolved_to_a_bool():
    for environment in ("development", "test", "staging", "production"):
        assert isinstance(_settings(environment).allow_bootstrap_registration, bool)


# --- what the endpoint does with it -----------------------------------------


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


BODY = {"email": "new-clin@example.org", "name": "Dr. New", "password": "password123"}


async def _existing_clinician(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_bootstrap_registration", True)
    res = await client.post("/api/auth/register", json={**BODY, "email": "first@example.org"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
async def test_in_production_by_default_nobody_signs_up_without_a_clinician(client, monkeypatch):
    prod = _settings("production")
    monkeypatch.setattr(settings, "allow_bootstrap_registration", prod.allow_bootstrap_registration)

    res = await client.post("/api/auth/register", json=BODY)

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_in_production_by_default_a_patient_cannot_create_a_clinician(client, monkeypatch, db_session):
    db_session.add(Patient(id="PREG1", name="Pat", age=40, sex="F", medical_record_number="PT-REG1"))
    await db_session.commit()
    db_session.add(
        User(
            id="u-pat-reg",
            email="pat-reg@example.org",
            name="Pat",
            hashed_password=await hash_password("password123"),
            role="patient",
            patient_id="PREG1",
        )
    )
    await db_session.commit()
    monkeypatch.setattr(
        settings, "allow_bootstrap_registration", _settings("production").allow_bootstrap_registration
    )

    res = await client.post(
        "/api/auth/register",
        json=BODY,
        headers={"Authorization": f"Bearer {create_access_token('u-pat-reg')}"},
    )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_in_production_by_default_a_signed_in_clinician_can_create_the_next_account(
    client, monkeypatch
):
    headers = await _existing_clinician(client, monkeypatch)
    monkeypatch.setattr(
        settings, "allow_bootstrap_registration", _settings("production").allow_bootstrap_registration
    )

    res = await client.post("/api/auth/register", json=BODY, headers=headers)

    assert res.status_code == 201 and res.json()["user"]["role"] == "clinician"


@pytest.mark.asyncio
async def test_in_development_by_default_registration_stays_open(client, monkeypatch):
    monkeypatch.setattr(
        settings, "allow_bootstrap_registration", _settings("development").allow_bootstrap_registration
    )

    res = await client.post("/api/auth/register", json=BODY)

    assert res.status_code == 201


@pytest.mark.asyncio
async def test_the_running_suite_has_registration_open_as_before(client):
    # conftest/CI run in development: the existing tests and smoke_test.sh rely on it.
    assert settings.allow_bootstrap_registration is True
    assert (await client.post("/api/auth/register", json=BODY)).status_code == 201


# --- the files that state it -------------------------------------------------


def test_render_keeps_saying_registration_is_closed():
    render = yaml.safe_load((REPO / "render.yaml").read_text())
    env = {v["key"]: v.get("value") for s in render["services"] for v in s["envVars"]}

    assert env["ALLOW_BOOTSTRAP_REGISTRATION"] == "false"
    assert env["ENVIRONMENT"] == "production"


def test_the_decision_is_written_down_with_its_triggers():
    adr = (REPO / "docs" / "08-decisions" / "ADR-021-single-shared-clinic.md").read_text()

    assert "Status:** Accepted" in adr
    for trigger in (
        "real (non-synthetic) patient data",
        "second clinic",
        "external clinicians",
        "AI_ALLOW_PHI",
    ):
        assert trigger in adr, trigger
    claude = (REPO / "CLAUDE.md").read_text()
    assert "ADR-021" in claude
    assert "ADR-021" in (REPO / "docs" / "05-operations" / "database-environments.md").read_text()
