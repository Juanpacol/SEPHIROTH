"""Deterministic confidence scoring.

Never LLM self-reported (ADR-008: "confidence must be derived, never
self-reported by the model"). Built entirely from signals already computed
elsewhere in the run — no new instrumentation, no embeddings, no model call.

Weights and the tool-failure cap are explicitly tunable (ADR-008 calls
abstention thresholds "a tunable, and tuning them is itself an experiment") —
kept as named constants here, not hardcoded inline, so a future tuning pass
against the eval harness has one place to change.
"""

from __future__ import annotations

from sephiroth.contracts import CitationReport, VerificationReport

FABRICATION_WEIGHT = 0.5
TOOL_FAILURE_WEIGHT = 0.2
TOOL_FAILURE_CAP = 3


def compute_confidence(
    report: VerificationReport, citation_report: CitationReport, tool_failures: int
) -> float:
    fabrication_rate = (
        len(citation_report.fabricated) / citation_report.total_checked
        if citation_report.total_checked
        else 0.0
    )
    capped_failures = min(max(tool_failures, 0), TOOL_FAILURE_CAP)

    confidence = (
        report.supported_claim_ratio
        * (1 - FABRICATION_WEIGHT * fabrication_rate)
        * (1 - TOOL_FAILURE_WEIGHT * capped_failures / TOOL_FAILURE_CAP)
    )
    return max(0.0, min(1.0, confidence))


__all__ = ["compute_confidence"]
