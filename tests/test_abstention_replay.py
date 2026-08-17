"""`intelligence.evaluation.abstention_replay` — wiring that replays
`sephiroth.verification`/`safety` over committed eval transcripts.

There is no ground truth yet for `CONFLICTING_EVIDENCE`/
`UNSUPPORTED_HIGH_RISK_CLAIM` — these tests exercise `INSUFFICIENT_EVIDENCE`
(the only branch the golden dataset's adversarial-negative cases cover) and
the pure metric math, which needs no LLM."""

import pytest

from intelligence.evaluation.abstention_replay import (
    build_verification_inputs,
    compute_abstention_metrics,
    replay_abstention,
)
from intelligence.evaluation.dataset import GoldenCase
from tests.conftest import FakeLLMClient


def _case(id_, expects_abstention=False):
    return GoldenCase(
        id=id_, query=f"query for {id_}", category="golden", expects_abstention=expects_abstention
    )


def test_build_verification_inputs_extracts_evidence_from_guideline_results():
    transcript = {
        "tool_calls": [
            {
                "name": "search_clinical_guidelines",
                "arguments": {"query": "x"},
                "result": {"results": [{"id": "d1", "content": "guideline text", "source": "ADA"}]},
            }
        ]
    }
    tool_calls, evidence = build_verification_inputs(transcript)
    assert len(tool_calls) == 1
    assert tool_calls[0].agent == "evidence"
    assert len(evidence) == 1
    assert evidence[0].content == "guideline text"


def test_build_verification_inputs_handles_no_evidence():
    transcript = {
        "tool_calls": [{"name": "search_clinical_guidelines", "arguments": {}, "result": {"results": []}}]
    }
    tool_calls, evidence = build_verification_inputs(transcript)
    assert len(tool_calls) == 1
    assert evidence == []


@pytest.mark.asyncio
async def test_replay_abstention_answers_by_default_when_no_claims_scripted():
    """The FakeLLMClient default (empty `json_payloads`) means
    `extract_claims` sees `{}` and returns no claims — `supported_claim_ratio`
    stays 1.0 and the replay answers, regardless of `expects_abstention`.
    Scripting a real claim extraction is required to exercise abstention at
    all (see the test below) — this pins the "nothing scripted" floor, same
    as the executor-level equivalent in test_runtime_executor.py."""
    case = _case("adv-1", expects_abstention=True)
    transcript = {"answer": "There is no relevant guideline for this.", "tool_calls": []}
    client = FakeLLMClient()

    result = await replay_abstention(case, transcript, client)

    assert result["case_id"] == "adv-1"
    assert result["expected_abstain"] is True
    assert result["actual_status"] == "answer"


@pytest.mark.asyncio
async def test_replay_abstention_abstains_on_insufficient_evidence():
    """A claim extracted with no evidence to verify it against (the exact
    shape of the 4 real `adversarial-negative` golden cases — no relevant
    document exists) makes `verify_claims` mark it `UNKNOWN` (its
    no-evidence short-circuit, before any verdict payload is even
    consulted), which zeroes `supported_claim_ratio` and drops confidence
    below `ABSTAIN_THRESHOLD` — this is the one `decide()` branch the
    golden dataset actually covers."""
    client = FakeLLMClient(json_payloads=[{"claims": [{"text": "no guideline covers this", "risk": "low"}]}])
    case = _case("adv-2", expects_abstention=True)
    transcript = {"answer": "no guideline covers this", "tool_calls": []}

    result = await replay_abstention(case, transcript, client)

    assert result["actual_status"] == "abstain"
    assert result["actual_reason"] == "insufficient_evidence"


def test_compute_abstention_metrics_perfect_recall_and_precision():
    results = [
        {"case_id": "adv-1", "expected_abstain": True, "actual_status": "abstain"},
        {"case_id": "adv-2", "expected_abstain": True, "actual_status": "abstain"},
        {"case_id": "golden-1", "expected_abstain": False, "actual_status": "answer"},
    ]
    metrics = compute_abstention_metrics(results)
    assert metrics["abstention_recall"] == 1.0
    assert metrics["abstention_precision"] == 1.0
    assert metrics["false_abstain_ids"] == []


def test_compute_abstention_metrics_false_abstain_lowers_precision():
    results = [
        {"case_id": "adv-1", "expected_abstain": True, "actual_status": "abstain"},
        {"case_id": "golden-1", "expected_abstain": False, "actual_status": "abstain"},
    ]
    metrics = compute_abstention_metrics(results)
    assert metrics["abstention_recall"] == 1.0
    assert metrics["abstention_precision"] == 0.5
    assert metrics["false_abstain_ids"] == ["golden-1"]


def test_compute_abstention_metrics_missed_abstain_lowers_recall():
    results = [
        {"case_id": "adv-1", "expected_abstain": True, "actual_status": "answer"},
        {"case_id": "golden-1", "expected_abstain": False, "actual_status": "answer"},
    ]
    metrics = compute_abstention_metrics(results)
    assert metrics["abstention_recall"] == 0.0
    assert metrics["abstention_precision"] == 1.0  # no abstains at all -> vacuously 1.0


def test_compute_abstention_metrics_no_cases_is_vacuous_perfect():
    metrics = compute_abstention_metrics([])
    assert metrics["abstention_recall"] == 1.0
    assert metrics["abstention_precision"] == 1.0
    assert metrics["total_cases"] == 0
