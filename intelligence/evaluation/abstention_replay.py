"""Replays `src/sephiroth/verification`/`safety` over committed transcripts.

Same pattern as `faithfulness.py::judge_llm`: this requires a live model
(claim extraction + verification are LLM calls), so it only ever runs inside
`runner.run_full_mode` and its output is read from the committed
`results/latest.json` snapshot in CI mode — never recomputed live in CI.

There is no ground truth yet for the `CONFLICTING_EVIDENCE` or
`UNSUPPORTED_HIGH_RISK_CLAIM` branches of `decide()` — the golden dataset's
4 `adversarial-negative` cases only exercise `INSUFFICIENT_EVIDENCE` (no
relevant document in the corpus at all). `abstention_recall`/`_precision`
below measure exactly that one branch; see `docs/specs/SPEC-004-verification-safety.md`
§11 risk 2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from intelligence.evaluation.dataset import GoldenCase
from sephiroth.contracts import CitationReport, EvidenceRecord, ToolCall
from sephiroth.models import ModelProvider
from sephiroth.runtime.executor import to_tool_calls
from sephiroth.safety import check_input, decide
from sephiroth.verification import compute_confidence, extract_claims, harvest_evidence, verify_claims

# Transcripts don't record a citation_guard.audit() verdict (only the
# answer/tool_calls), so every replayed case is treated as zero-fabrication
# input — this only affects the `fabrication_rate` term of
# `compute_confidence`, not the claim-verification pipeline itself.


def build_verification_inputs(transcript: Dict[str, Any]) -> tuple[List[ToolCall], List[EvidenceRecord]]:
    """Converts a committed transcript's raw `tool_calls` into the typed
    records `sephiroth.verification` expects — the same conversion
    `sephiroth.runtime.executor` does live, reused here via `to_tool_calls`."""
    tool_calls = to_tool_calls("evidence", transcript.get("tool_calls", []))
    evidence = harvest_evidence(tool_calls)
    return tool_calls, evidence


async def replay_abstention(
    case: GoldenCase, transcript: Dict[str, Any], client: ModelProvider
) -> Dict[str, Any]:
    """Runs the live verification/abstention pipeline over one transcript's
    recorded answer, returning the decision alongside the case's expectation."""
    tool_calls, evidence = build_verification_inputs(transcript)
    answer = transcript.get("answer", "")

    claims = await extract_claims(answer, client)
    report = await verify_claims(claims, evidence, client)
    tool_failures = sum(1 for tc in tool_calls if not tc.ok)
    citation_report = CitationReport()  # see module docstring
    confidence = compute_confidence(report, citation_report, tool_failures)
    input_flags = check_input(case.query)
    abstention = decide(report, confidence, input_flags)

    return {
        "case_id": case.id,
        "expected_abstain": case.expects_abstention,
        "actual_status": abstention.status.value,
        "actual_reason": abstention.reason.value if abstention.reason else None,
        "confidence": confidence,
    }


def compute_abstention_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic, no LLM: precision/recall of the `abstain` decision
    against `expects_abstention` labels.

    `abstention_recall` — of the cases that SHOULD abstain, how many did.
    `abstention_precision` — of the cases that DID abstain, how many should have.
    Per ADR-008, these must always be reported as a pair — a system that
    abstains on everything scores perfect recall and is worthless; precision
    is what catches that.
    """
    should_abstain = [r for r in results if r["expected_abstain"]]
    did_abstain = [r for r in results if r["actual_status"] == "abstain"]
    true_positives = [r for r in did_abstain if r["expected_abstain"]]
    false_abstain_ids = [r["case_id"] for r in did_abstain if not r["expected_abstain"]]

    recall = len(true_positives) / len(should_abstain) if should_abstain else 1.0
    precision = len(true_positives) / len(did_abstain) if did_abstain else 1.0

    return {
        "abstention_recall": round(recall, 4),
        "abstention_precision": round(precision, 4),
        "total_cases": len(results),
        "total_expected_abstain": len(should_abstain),
        "total_actual_abstain": len(did_abstain),
        "false_abstain_ids": false_abstain_ids,
    }


__all__ = ["build_verification_inputs", "compute_abstention_metrics", "replay_abstention"]
