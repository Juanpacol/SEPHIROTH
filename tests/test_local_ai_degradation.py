"""What happens when the model is not there.

A local-first deployment loses its model more often than a hosted one does —
someone reboots the machine, `ollama serve` is not running yet, a pull is still
downloading. So "the model is down" stops being an incident and becomes an
ordinary state the product has to behave well in.

Two things follow. A question that never needed a model must still be answered:
"does warfarin interact with aspirin" is a lookup in a local table with its own
citation, and refusing it because a *language model* is unavailable is refusing
work the machine can do. And the refusal a clinician does see must name the
thing that is actually broken — the old message blamed Gemini and told them to
check `GEMINI_API_KEY` even on a stack that had never been near Google, which
sends whoever is on call to look in the wrong place.

Verifies AC-022-07 (docs/specs/SPEC-022-local-ai.md).
"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import sephiroth.models.factory as factory_module
from api.intelligence.routers import agents as agents_router_module
from auth import router as auth_router_module
from core.db import get_session
from sephiroth.models import LLMUnavailableError, ProviderInfo

CREDS = {"email": "degradation@example.org", "name": "Dr. Offline", "password": "password123"}


class _DeadOllama:
    """A local model that is not running. Every method raises rather than
    returning something plausible: a test that passes because the double
    answered is not testing degradation."""

    model = "qwen2.5:14b"
    supports_vision = False
    supports_tools = True

    async def health(self) -> bool:
        return False

    async def chat(self, *args, **kwargs):
        raise LLMUnavailableError("connection refused")

    async def generate_json(self, *args, **kwargs):
        raise LLMUnavailableError("connection refused")

    async def describe_image(self, *args, **kwargs):
        raise LLMUnavailableError("connection refused")

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            provider="ollama",
            model=self.model,
            local=True,
            endpoint="localhost",
        )


@pytest.fixture
def dead_model(db_session, monkeypatch):
    monkeypatch.setattr(factory_module, "_client", _DeadOllama())

    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(agents_router_module, "SessionLocal", lambda: _session_cm())

    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(agents_router_module.router, prefix="/api/agents")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def offline_client(dead_model):
    async with AsyncClient(transport=ASGITransport(app=dead_model), base_url="http://test") as client:
        token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
        yield client, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestAConsultationThatNeverNeededAModel:
    async def test_a_drug_interaction_question_is_still_answered(self, offline_client):
        """AC-022-07. The answer comes from a local interaction table, so the
        language model being down is irrelevant to it."""
        client, headers = offline_client

        res = await client.post(
            "/api/agents/consult",
            json={"query": "Does warfarin interact with aspirin?", "patient_id": ""},
            headers=headers,
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer"]
        assert body["agents_involved"] == ["drug-safety"]

    async def test_the_streaming_path_answers_it_too(self, offline_client):
        client, headers = offline_client

        res = await client.post(
            "/api/agents/consult/stream",
            json={"query": "Does warfarin interact with aspirin?", "patient_id": ""},
            headers=headers,
        )

        assert res.status_code == 200
        assert "drug-safety" in res.text


@pytest.mark.asyncio
class TestTheRefusalNamesWhatIsActuallyBroken:
    async def test_a_question_needing_a_model_is_refused_by_the_real_provider(self, offline_client):
        client, headers = offline_client

        res = await client.post(
            "/api/agents/consult",
            json={"query": "Summarise this patient's cardiac history.", "patient_id": ""},
            headers=headers,
        )

        assert res.status_code == 503
        detail = res.json()["detail"]
        assert "ollama" in detail
        assert "qwen2.5:14b" in detail
        # The old message said this on a stack that had never touched Google.
        assert "GEMINI_API_KEY" not in detail

    async def test_it_says_what_to_check(self, offline_client):
        """An operator reading this should know the next command to run."""
        client, headers = offline_client

        res = await client.post(
            "/api/agents/consult",
            json={"query": "Summarise this patient's cardiac history.", "patient_id": ""},
            headers=headers,
        )

        assert "ollama serve" in res.json()["detail"]


@pytest.mark.asyncio
class TestDraftsKeepTheirTemplate:
    async def test_an_unreachable_model_leaves_the_deterministic_draft_in_place(self, monkeypatch):
        """AC-022-07's other half (B-11). A clinician who opens the approval
        queue during an outage still has something reviewable to send."""
        from intelligence.mcp import patient_comms_server

        monkeypatch.setattr(patient_comms_server, "get_llm_client", lambda: _DeadOllama())

        with pytest.raises(LLMUnavailableError):
            await patient_comms_server.draft_message(
                purpose="followup_check", patient_first_name="Ana", facts={}
            )

        # The router's contract is that this exception is caught and the
        # template is kept — asserted end to end in
        # `tests/test_approval_draft_endpoint.py`. What matters here is that
        # the failure is the catchable kind rather than something the caller
        # has no handler for.


@pytest.mark.asyncio
class TestTimelineExtractionFallsBackToTheLexicon:
    async def test_a_note_still_produces_a_timeline_with_no_model(self):
        from intelligence.nlp.timeline_extractor import extract_events

        events = await extract_events(
            _DeadOllama(), "2026-09-01: Started metformin 500mg for type 2 diabetes.", "2026-09-01"
        )

        assert isinstance(events, list)
