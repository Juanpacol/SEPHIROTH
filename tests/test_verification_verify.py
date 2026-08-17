"""`verify_claims` — batched claim/evidence verification, one `generate_json`
call per consultation, plus the deterministic token-overlap downgrade rule
that mitigates ADR-006's "the judge can be wrong" risk.

Verifies AC-004-02, AC-004-03 (docs/specs/SPEC-004-verification-safety.md)."""

from datetime import datetime, timezone

import pytest

from sephiroth.contracts import (
    Citation,
    Claim,
    EvidenceRecord,
    RetrievalMethod,
    SourceType,
    VerificationStatus,
)
from sephiroth.verification.verify import verify_claims
from tests.conftest import FakeLLMClient


def _evidence(id_, content, source="ADA"):
    return EvidenceRecord(
        id=id_,
        source=source,
        source_type=SourceType.GUIDELINE,
        retrieval_method=RetrievalMethod.TOOL,
        citation=Citation(label=source),
        originating_agent="evidence",
        timestamp=datetime.now(timezone.utc),
        content=content,
    )


@pytest.mark.asyncio
async def test_no_claims_returns_empty_report():
    report = await verify_claims([], [], FakeLLMClient())
    assert report.claims == []
    assert report.contradictions == []


@pytest.mark.asyncio
async def test_no_evidence_marks_every_claim_unknown_not_supported():
    claims = [Claim(id="c1", text="metformin is first-line")]
    report = await verify_claims(claims, [], FakeLLMClient())
    assert report.claims[0].status is VerificationStatus.UNKNOWN


@pytest.mark.asyncio
async def test_scripted_supported_verdict_with_real_overlap_stays_supported():
    claims = [Claim(id="c1", text="An A1C goal of less than 7 percent is appropriate")]
    evidence = [_evidence("e1", "An A1C goal of <7% is appropriate for most adults with diabetes.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "verdicts": [
                    {"claim_id": "c1", "status": "supported", "evidence_ids": ["e1"], "confidence": 0.9}
                ]
            }
        ]
    )
    report = await verify_claims(claims, evidence, client)
    assert report.claims[0].status is VerificationStatus.SUPPORTED
    assert report.claims[0].evidence_ids == ["e1"]


@pytest.mark.asyncio
async def test_supported_verdict_with_no_token_overlap_is_downgraded():
    claims = [Claim(id="c1", text="Increase insulin dosage immediately")]
    evidence = [_evidence("e1", "Metformin remains the preferred initial pharmacologic agent.")]
    client = FakeLLMClient(
        json_payloads=[{"verdicts": [{"claim_id": "c1", "status": "supported", "evidence_ids": ["e1"]}]}]
    )
    report = await verify_claims(claims, evidence, client)
    assert report.claims[0].status is VerificationStatus.PARTIALLY_SUPPORTED
    assert "downgraded" in report.claims[0].rationale


@pytest.mark.asyncio
async def test_claim_with_no_verdict_defaults_to_unknown():
    claims = [Claim(id="c1", text="x"), Claim(id="c2", text="y")]
    evidence = [_evidence("e1", "y is well supported by this passage")]
    client = FakeLLMClient(json_payloads=[{"verdicts": [{"claim_id": "c2", "status": "unsupported"}]}])
    report = await verify_claims(claims, evidence, client)
    by_id = {c.id: c for c in report.claims}
    assert by_id["c1"].status is VerificationStatus.UNKNOWN
    assert by_id["c2"].status is VerificationStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_contradictions_are_parsed():
    claims = [Claim(id="c1", text="x"), Claim(id="c2", text="not x")]
    evidence = [_evidence("e1", "some content")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "verdicts": [
                    {"claim_id": "c1", "status": "contradicted"},
                    {"claim_id": "c2", "status": "supported"},
                ],
                "contradictions": [
                    {"claim_id": "c1", "conflicting_claim_id": "c2", "description": "direct conflict"}
                ],
            }
        ]
    )
    report = await verify_claims(claims, evidence, client)
    assert len(report.contradictions) == 1
    assert report.contradictions[0].conflicting_claim_id == "c2"


@pytest.mark.asyncio
async def test_generate_json_failure_degrades_every_claim_to_unknown():
    class _BoomClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, system_prompt=None):
            raise RuntimeError("LLM unavailable")

    claims = [Claim(id="c1", text="x")]
    evidence = [_evidence("e1", "content")]
    report = await verify_claims(claims, evidence, _BoomClient())
    assert report.claims[0].status is VerificationStatus.UNKNOWN


@pytest.mark.asyncio
async def test_invalid_status_value_defaults_to_unknown():
    claims = [Claim(id="c1", text="x")]
    evidence = [_evidence("e1", "content")]
    client = FakeLLMClient(json_payloads=[{"verdicts": [{"claim_id": "c1", "status": "maybe"}]}])
    report = await verify_claims(claims, evidence, client)
    assert report.claims[0].status is VerificationStatus.UNKNOWN


@pytest.mark.asyncio
async def test_non_dict_payload_treated_as_empty():
    claims = [Claim(id="c1", text="x")]
    evidence = [_evidence("e1", "content")]
    client = FakeLLMClient(json_payloads=["not a dict"])
    report = await verify_claims(claims, evidence, client)
    assert report.claims[0].status is VerificationStatus.UNKNOWN


@pytest.mark.asyncio
async def test_supported_verdict_citing_unknown_evidence_id_is_downgraded():
    """`_overlap_supports` must not crash or silently trust a verdict that
    cites an evidence id the harvester never produced."""
    claims = [Claim(id="c1", text="x")]
    evidence = [_evidence("e1", "some real content")]
    client = FakeLLMClient(
        json_payloads=[
            {"verdicts": [{"claim_id": "c1", "status": "supported", "evidence_ids": ["nonexistent"]}]}
        ]
    )
    report = await verify_claims(claims, evidence, client)
    assert report.claims[0].status is VerificationStatus.PARTIALLY_SUPPORTED
