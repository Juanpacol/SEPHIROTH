"""`extract_claims` — decomposes an answer into `Claim`s via a scripted
`generate_json` response (`FakeLLMClient.json_payloads`).

Verifies AC-004-01 (docs/specs/SPEC-004-verification-safety.md)."""

import pytest

from sephiroth.contracts import RiskLevel
from sephiroth.verification.claims import extract_claims
from tests.conftest import FakeLLMClient


@pytest.mark.asyncio
async def test_empty_answer_returns_no_claims():
    client = FakeLLMClient()
    assert await extract_claims("", client) == []
    assert await extract_claims("   ", client) == []


@pytest.mark.asyncio
async def test_extracts_claims_from_scripted_payload():
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {
                        "text": "Metformin is first-line therapy.",
                        "originating_agent": "evidence",
                        "risk": "low",
                    },
                    {
                        "text": "Increase warfarin dose by 50%.",
                        "originating_agent": "drug_safety",
                        "risk": "high",
                    },
                ]
            }
        ]
    )
    claims = await extract_claims("Metformin is first-line therapy. Increase warfarin dose by 50%.", client)

    assert len(claims) == 2
    assert claims[0].text == "Metformin is first-line therapy."
    assert claims[0].originating_agent == "evidence"
    assert claims[0].risk is RiskLevel.LOW
    assert claims[1].risk is RiskLevel.HIGH
    assert claims[0].id != claims[1].id


@pytest.mark.asyncio
async def test_blank_claim_text_is_skipped():
    client = FakeLLMClient(json_payloads=[{"claims": [{"text": ""}, {"text": "  "}, {"text": "real claim"}]}])
    claims = await extract_claims("real claim", client)
    assert len(claims) == 1
    assert claims[0].text == "real claim"


@pytest.mark.asyncio
async def test_invalid_risk_value_defaults_to_high():
    """Fail-safe, not fail-open: a missing/malformed risk value must default
    to HIGH so the abstention gate's unsupported-high-risk check still
    applies — defaulting to LOW would silently exempt the claim."""
    client = FakeLLMClient(json_payloads=[{"claims": [{"text": "x", "risk": "extreme"}]}])
    claims = await extract_claims("x", client)
    assert claims[0].risk is RiskLevel.HIGH


@pytest.mark.asyncio
async def test_generate_json_failure_degrades_to_no_claims():
    class _BoomClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, system_prompt=None):
            raise RuntimeError("LLM unavailable")

    claims = await extract_claims("some answer", _BoomClient())
    assert claims == []


@pytest.mark.asyncio
async def test_non_dict_payload_degrades_to_no_claims():
    client = FakeLLMClient(json_payloads=["not a dict"])
    assert await extract_claims("answer", client) == []


@pytest.mark.asyncio
async def test_non_dict_claim_entries_are_skipped():
    client = FakeLLMClient(json_payloads=[{"claims": ["not a dict", {"text": "real claim"}]}])
    claims = await extract_claims("real claim", client)
    assert len(claims) == 1
    assert claims[0].text == "real claim"
