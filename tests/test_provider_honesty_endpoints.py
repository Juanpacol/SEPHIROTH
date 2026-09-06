"""The three endpoints that used to name the wrong model.

Each of them answered "what is running" from `settings.gemini_*` or from a
literal, whatever the configured provider was. An operator running the whole
stack on a local Ollama was told the model was Gemini and that `local_only` was
False. Being wrong in that direction is worse than saying nothing: it teaches
people the field cannot be trusted, and then the field is useless on the day it
matters.

Verifies AC-022-04 (docs/specs/SPEC-022-local-ai.md).
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import sephiroth.models.factory as factory_module
from api.main import app
from api.routers import agents as agents_router_module
from auth import router as auth_router_module
from core.db import get_session

CREDS = {"email": "provider-honesty@example.org", "name": "Dr. Honest", "password": "password123"}


@pytest.fixture
async def agents_client(db_session):
    """A logged-in clinician against the agents router alone.

    `/api/agents/status` is behind the clinician guard, and the full `app`
    fixture would need a database the other tests here deliberately do not
    touch.
    """
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(agents_router_module.router, prefix="/api/agents")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
        yield client, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def provider(monkeypatch):
    """Rebuild the factory's client under a given configuration."""

    def _set(**overrides):
        from core.config import Settings

        settings = Settings(_env_file=None, environment="development", **overrides)
        monkeypatch.setattr(factory_module, "settings", settings)
        monkeypatch.setattr(factory_module, "_client", None)
        import core.config as config_module

        monkeypatch.setattr(config_module, "settings", settings)
        # Modules that did `from core.config import settings` hold their own
        # binding, so patching the source alone would leave them on the old
        # object -- the same reason `test_llm_factory` patches the factory's.
        monkeypatch.setattr(agents_router_module, "settings", settings)
        return settings

    return _set


async def _get(path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
class TestHealth:
    async def test_it_names_the_running_model_not_geminis(self, provider):
        provider()  # defaults: local Ollama

        body = (await _get("/health")).json()

        assert body["status"] == "healthy"
        assert body["provider"] == "ollama"
        assert body["local_only"] is True
        assert "gemini" not in body["model"]

    async def test_it_names_gemini_when_gemini_is_what_is_running(self, provider):
        provider(llm_provider="gemini", gemini_api_key="fake-gemini-key")

        body = (await _get("/health")).json()

        assert body["provider"] == "gemini"
        assert body["local_only"] is False

    async def test_it_opens_no_connection(self, provider, monkeypatch):
        """AC-022-04's second half. This is Render's liveness path: making it
        probe anything would let a third party's blip restart the instance."""
        provider()
        client = factory_module.get_llm_client()

        async def _explode():
            raise AssertionError("/health performed I/O")

        monkeypatch.setattr(client, "health", _explode)

        assert (await _get("/health")).status_code == 200


@pytest.mark.asyncio
class TestReadiness:
    async def test_a_local_deployment_with_no_gemini_key_is_not_reported_unconfigured(
        self, provider, monkeypatch
    ):
        """The old check asked whether `GEMINI_API_KEY` was set, which
        describes the default deployment — the one this phase makes standard —
        as unconfigured while it is serving correctly."""
        provider()
        monkeypatch.setattr(factory_module.get_llm_client(), "health", _ok)

        checks = (await _get("/health/ready")).json()["checks"]

        assert checks["llm"] == "ok"
        assert checks["llm_provider"] == "ollama"

    async def test_a_model_that_is_down_is_reported_unreachable(self, provider, monkeypatch):
        provider()
        monkeypatch.setattr(factory_module.get_llm_client(), "health", _down)

        body = (await _get("/health/ready")).json()

        assert body["checks"]["llm"] == "unreachable"

    async def test_a_model_that_is_down_does_not_take_the_instance_out_of_rotation(
        self, provider, monkeypatch
    ):
        """Losing the model degrades features (B-10/B-11). The database is the
        dependency this instance cannot serve without."""
        provider()
        monkeypatch.setattr(factory_module.get_llm_client(), "health", _down)

        body = (await _get("/health/ready")).json()

        assert body["checks"]["database"] == "ok"
        assert body["status"] == "ready"


async def _ok() -> bool:
    return True


async def _down() -> bool:
    return False


@pytest.mark.asyncio
class TestAgentStatus:
    async def _status(self, client, headers):
        return (await client.get("/api/agents/status", headers=headers)).json()

    async def test_it_reports_the_real_provider_and_locality(self, provider, agents_client):
        client, headers = agents_client
        provider()

        system = (await self._status(client, headers))["system"]

        assert system["provider"] == "ollama"
        assert system["local_only"] is True
        assert "gemini" not in system["model"]

    async def test_it_states_what_the_deployment_does_with_patient_content(self, provider, agents_client):
        client, headers = agents_client
        provider(llm_provider="gemini", gemini_api_key="fake-gemini-key", ai_allow_phi=True)

        system = (await self._status(client, headers))["system"]

        assert system["provider"] == "gemini"
        assert system["local_only"] is False
        assert system["phi_allowed"] is True

    async def test_a_split_deployment_shows_both_halves(self, provider, agents_client):
        client, headers = agents_client
        provider(llm_provider="split", gemini_api_key="fake-gemini-key")

        system = (await self._status(client, headers))["system"]

        assert system["provider"] == "split"
        # The vision half reaches Google, so the deployment is not local — the
        # exact case the old hardcoded `local_only` could never express.
        assert system["local_only"] is False
        assert [c["provider"] for c in system["components"]] == ["ollama", "gemini"]
