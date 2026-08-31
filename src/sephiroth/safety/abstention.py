"""Abstention gating — the actual safety decision.

The priority order below *is* the design: a policy violation or an
unsupported high-risk claim must short-circuit before any confidence
threshold is even consulted. An answer that "sounds confident" but asserts
one unsupported high-risk claim must still abstain — that invariant, from
`docs/06-security/safety.md`, is what makes this a safety gate and not a
quality score.
"""

from __future__ import annotations

from typing import List

from sephiroth.contracts import (
    AbstentionDecision,
    AbstentionReason,
    ResponseStatus,
    SafetyFlag,
    VerificationReport,
)

# Tunable per ADR-008 ("tuning them is itself an experiment") — validate
# against the eval harness before hardening these further.
ABSTAIN_THRESHOLD = 0.4
PARTIAL_THRESHOLD = 0.65

PARTIAL_BANNER = (
    "Note: this answer has moderate confidence — some claims could not be "
    "fully verified against retrieved evidence. Please review carefully."
)

_ABSTAIN_MESSAGES = {
    AbstentionReason.POLICY_RESTRICTION: (
        "This request could not be safely processed. Please rephrase your clinical question."
    ),
    AbstentionReason.OUT_OF_SCOPE: (
        "This looks like a non-clinical question. I can only help with medical "
        "and clinical topics — please rephrase as a clinical question."
    ),
    AbstentionReason.UNSUPPORTED_HIGH_RISK_CLAIM: (
        "I can't confidently answer this — a high-risk claim in this response "
        "isn't backed by strong supporting evidence. Please consult the "
        "relevant specialist or guideline directly."
    ),
    AbstentionReason.CONFLICTING_EVIDENCE: (
        "The retrieved evidence conflicts on this question. Please consult the "
        "relevant specialist or guideline directly rather than relying on this answer."
    ),
    AbstentionReason.INSUFFICIENT_EVIDENCE: (
        "There isn't enough verified evidence to answer this confidently. "
        "Please consult the relevant specialist or guideline directly."
    ),
}


def _abstain(reason: AbstentionReason, confidence: float, ratio: float) -> AbstentionDecision:
    return AbstentionDecision(
        status=ResponseStatus.ABSTAIN,
        reason=reason,
        confidence=confidence,
        supported_claim_ratio=ratio,
        message=_ABSTAIN_MESSAGES[reason],
    )


def decide(
    report: VerificationReport, confidence: float, input_flags: List[SafetyFlag]
) -> AbstentionDecision:
    """Priority order: policy/scope > unsupported high-risk claim >
    contradiction > confidence thresholds. Each earlier check overrides a
    later, more lenient one. `out_of_scope` sits at the same priority as
    `prompt_injection` — both are input-level hard stops decided before any
    evidence-based reasoning is even consulted; see `runtime/executor.py`,
    which checks these flags before routing so an off-topic question never
    reaches a specialist or a model call at all."""
    ratio = report.supported_claim_ratio

    if any(flag.code == "prompt_injection" for flag in input_flags):
        return _abstain(AbstentionReason.POLICY_RESTRICTION, confidence, ratio)
    if any(flag.code == "out_of_scope" for flag in input_flags):
        return _abstain(AbstentionReason.OUT_OF_SCOPE, confidence, ratio)
    if report.has_unsupported_high_risk_claim:
        return _abstain(AbstentionReason.UNSUPPORTED_HIGH_RISK_CLAIM, confidence, ratio)
    if report.contradictions:
        return _abstain(AbstentionReason.CONFLICTING_EVIDENCE, confidence, ratio)
    if confidence < ABSTAIN_THRESHOLD:
        return _abstain(AbstentionReason.INSUFFICIENT_EVIDENCE, confidence, ratio)
    if confidence < PARTIAL_THRESHOLD:
        return AbstentionDecision(
            status=ResponseStatus.PARTIAL, confidence=confidence, supported_claim_ratio=ratio
        )
    return AbstentionDecision(
        status=ResponseStatus.ANSWER, confidence=confidence, supported_claim_ratio=ratio
    )


__all__ = ["ABSTAIN_THRESHOLD", "PARTIAL_BANNER", "PARTIAL_THRESHOLD", "decide"]
