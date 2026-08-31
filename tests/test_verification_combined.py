"""`extract_and_verify` — the merged decompose-and-judge call that replaces
the two sequential `extract_claims` → `verify_claims` round-trips.

The merge is only safe if it keeps every guarantee the two-call path had,
so this file mirrors the assertions in `test_verification_claims.py` and
`test_verification_verify.py` rather than testing the happy path alone:
the low-overlap downgrade (ADR-006's mitigation for "the judge is itself
an LLM"), no-evidence ⇒ `unknown` never `supported`, and degrade-to-empty
on every malformed payload."""

from datetime import datetime, timezone

import pytest

from sephiroth.contracts import (
    Citation,
    EvidenceRecord,
    RetrievalMethod,
    RiskLevel,
    SourceType,
    VerificationStatus,
)
from sephiroth.verification.combined import extract_and_verify
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.asyncio

ANSWER = "Metformin is first-line therapy for type 2 diabetes."


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


# --------------------------------------------------------------------------
# Happy path — one call yields claims already carrying verdicts
# --------------------------------------------------------------------------


async def test_single_call_returns_claims_with_verdicts():
    evidence = [_evidence("e1", "Metformin is the preferred initial agent for type 2 diabetes.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "Metformin is first-line therapy for type 2 diabetes",
                        "originating_agent": "evidence",
                        "risk": "medium",
                        "status": "supported",
                        "evidence_ids": ["e1"],
                        "confidence": 0.9,
                        "rationale": "directly stated",
                    }
                ]
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)

    assert len(report.claims) == 1
    claim = report.claims[0]
    assert claim.status is VerificationStatus.SUPPORTED
    assert claim.risk is RiskLevel.MEDIUM
    assert claim.originating_agent == "evidence"
    assert claim.evidence_ids == ["e1"]
    assert claim.confidence == 0.9
    # Exactly one model round-trip — that is the entire point of the merge.
    assert len(client.json_payloads) == 0


async def test_schema_echo_still_yields_claims():
    """A model that returns the JSON Schema envelope with its values filled in
    under `properties` must not read as "the answer asserted nothing" — that
    would report a clean verification pass while having verified nothing.
    Observed with qwen2.5:3b-instruct before the client constrained decoding
    to the schema; kept as the guard against any provider drifting back."""
    evidence = [_evidence("e1", "Metformin is the preferred initial agent for type 2 diabetes.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "type": "object",
                "properties": {
                    "claims": [
                        {
                            "id": "c1",
                            "text": "Metformin is first-line therapy for type 2 diabetes",
                            "risk": "medium",
                            "status": "supported",
                            "evidence_ids": ["e1"],
                            "confidence": 0.9,
                        }
                    ],
                    "contradictions": [],
                },
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)

    assert len(report.claims) == 1
    assert report.claims[0].status is VerificationStatus.SUPPORTED


async def test_evidence_is_referenced_by_short_alias_not_raw_uuid():
    """Real `EvidenceRecord.id`s are 32-char uuid4 hex. The prompt shows short
    aliases instead, because a model that mistypes the id has its verdict
    dropped, loses `_overlap_supports`, and gets a correct `supported`
    downgraded — abstaining on a well-grounded answer."""
    uuid_id = "f08d89f14db54f32a70f3cd3f505bc34"
    evidence = [_evidence(uuid_id, "Metformin is the preferred initial agent for type 2 diabetes.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {
                        "text": "Metformin is first-line therapy for type 2 diabetes",
                        "status": "supported",
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)

    assert client.last_prompt is not None
    assert "id=e1" in client.last_prompt
    assert uuid_id not in client.last_prompt
    # The alias resolves back to the real id, so the record still joins.
    assert report.claims[0].evidence_ids == [uuid_id]
    assert report.claims[0].status is VerificationStatus.SUPPORTED


async def test_contradictions_are_returned():
    evidence = [_evidence("e1", "Metformin is the preferred initial agent for type 2 diabetes.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {"id": "c1", "text": "metformin is first-line", "status": "supported",
                     "evidence_ids": ["e1"]},
                    {"id": "c2", "text": "metformin is contraindicated", "status": "unsupported"},
                ],
                "contradictions": [
                    {"claim_id": "c1", "conflicting_claim_id": "c2", "description": "opposite advice"}
                ],
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].claim_id == "c1"
    assert report.contradictions[0].conflicting_claim_id == "c2"


async def test_contradiction_referencing_an_unknown_claim_is_dropped():
    """A hallucinated claim_id must not create a phantom contradiction —
    the abstention gate treats any contradiction as grounds to abstain."""
    evidence = [_evidence("e1", "Metformin is preferred.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [{"id": "c1", "text": "metformin is first-line", "status": "supported",
                            "evidence_ids": ["e1"]}],
                "contradictions": [{"claim_id": "does-not-exist", "description": "phantom"}],
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)
    assert report.contradictions == []


# --------------------------------------------------------------------------
# ADR-006 mitigation — never trust the judge alone
# --------------------------------------------------------------------------


async def test_supported_verdict_downgraded_when_evidence_shares_no_vocabulary():
    """The deterministic guard carried over from `verify.py`: a `supported`
    claim whose cited evidence shares almost no tokens with it is demoted
    to `partially_supported`."""
    evidence = [_evidence("e1", "Colorectal cancer screening should begin at age 45.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "Warfarin dosing requires INR monitoring",
                        "status": "supported",
                        "evidence_ids": ["e1"],
                        "confidence": 0.95,
                    }
                ]
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)

    assert report.claims[0].status is VerificationStatus.PARTIALLY_SUPPORTED
    assert "downgraded" in report.claims[0].rationale


async def test_evidence_ids_outside_the_provided_set_are_dropped():
    evidence = [_evidence("e1", "Metformin is the preferred initial agent.")]
    client = FakeLLMClient(
        json_payloads=[
            {
                "claims": [
                    {"id": "c1", "text": "metformin is preferred initial agent", "status": "supported",
                     "evidence_ids": ["e1", "hallucinated-id"]}
                ]
            }
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)
    assert report.claims[0].evidence_ids == ["e1"]


# --------------------------------------------------------------------------
# No evidence — unknown, never supported
# --------------------------------------------------------------------------


async def test_no_evidence_marks_every_claim_unknown():
    """With nothing to judge against, claims are still extracted (the
    abstention gate needs to see a high-risk claim was made) but no verdict
    may be positive."""
    client = FakeLLMClient(
        json_payloads=[
            {"claims": [{"text": "Double the warfarin dose", "risk": "critical"}]}
        ]
    )

    report = await extract_and_verify(ANSWER, [], client)

    assert len(report.claims) == 1
    assert report.claims[0].status is VerificationStatus.UNKNOWN
    assert report.claims[0].risk is RiskLevel.CRITICAL


# --------------------------------------------------------------------------
# Degradation — every failure yields an empty report, never a false pass
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},  # no claims key
        {"claims": "not-a-list"},
        {"claims": [{"text": ""}]},  # empty text
        {"claims": ["not-a-dict"]},
        None,
        ["not-a-dict-at-all"],
    ],
)
async def test_malformed_payload_degrades_to_empty_report(payload):
    evidence = [_evidence("e1", "some content")]
    report = await extract_and_verify(ANSWER, evidence, FakeLLMClient(json_payloads=[payload]))
    assert report.claims == []
    assert report.contradictions == []


async def test_model_exception_degrades_to_empty_report():
    class _RaisingClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, *, system_prompt=None):
            raise RuntimeError("model unavailable")

    report = await extract_and_verify(ANSWER, [_evidence("e1", "x")], _RaisingClient())
    assert report.claims == []


async def test_empty_answer_returns_empty_report_without_calling_the_model():
    class _NoCallClient(FakeLLMClient):
        async def generate_json(self, prompt, schema, *, system_prompt=None):
            raise AssertionError("should not call the model for an empty answer")

    report = await extract_and_verify("   ", [_evidence("e1", "x")], _NoCallClient())
    assert report.claims == []


async def test_unparseable_status_or_risk_falls_back_safely():
    """A bad enum value must not raise, and must not become a positive
    verdict — `unknown` status and `high` risk are the safe defaults (fail
    fail-safe, not fail-open: HIGH keeps the abstention gate's
    unsupported-high-risk check applying instead of silently exempting the
    claim)."""
    evidence = [_evidence("e1", "Metformin is preferred.")]
    client = FakeLLMClient(
        json_payloads=[
            {"claims": [{"id": "c1", "text": "metformin is preferred", "status": "bogus", "risk": "bogus"}]}
        ]
    )

    report = await extract_and_verify(ANSWER, evidence, client)
    assert report.claims[0].status is VerificationStatus.UNKNOWN
    assert report.claims[0].risk is RiskLevel.HIGH


async def test_claim_without_an_id_still_survives():
    """Ids come from the model here (it needs them to reference claims from
    `contradictions`); a missing one must not silently drop the claim."""
    evidence = [_evidence("e1", "Metformin is preferred.")]
    client = FakeLLMClient(
        json_payloads=[{"claims": [{"text": "metformin is preferred", "status": "unsupported"}]}]
    )

    report = await extract_and_verify(ANSWER, evidence, client)
    assert len(report.claims) == 1
    assert report.claims[0].id  # generated
