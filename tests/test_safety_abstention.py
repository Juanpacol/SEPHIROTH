"""`decide` — the priority-ordered abstention gate. Each test isolates one
priority level to prove earlier checks override later, more lenient ones.

Verifies AC-004-05 (docs/specs/SPEC-004-verification-safety.md)."""

from sephiroth.contracts import (
    AbstentionReason,
    Claim,
    Contradiction,
    ResponseStatus,
    RiskLevel,
    SafetyFlag,
    VerificationReport,
    VerificationStatus,
)
from sephiroth.safety.abstention import ABSTAIN_THRESHOLD, PARTIAL_THRESHOLD, decide


def test_high_confidence_no_claims_answers():
    report = VerificationReport()
    decision = decide(report, confidence=1.0, input_flags=[])
    assert decision.status is ResponseStatus.ANSWER
    assert decision.reason is None


def test_low_confidence_abstains_with_insufficient_evidence():
    report = VerificationReport()
    decision = decide(report, confidence=ABSTAIN_THRESHOLD - 0.01, input_flags=[])
    assert decision.status is ResponseStatus.ABSTAIN
    assert decision.reason is AbstentionReason.INSUFFICIENT_EVIDENCE


def test_mid_confidence_is_partial_not_abstain():
    report = VerificationReport()
    decision = decide(report, confidence=(ABSTAIN_THRESHOLD + PARTIAL_THRESHOLD) / 2, input_flags=[])
    assert decision.status is ResponseStatus.PARTIAL
    assert decision.reason is None


def test_unsupported_high_risk_claim_abstains_even_with_high_confidence():
    """The single most important safety signal: a high-confidence-looking
    answer must still abstain if it asserts one unsupported high-risk claim."""
    report = VerificationReport(
        claims=[Claim(id="c1", text="x", risk=RiskLevel.HIGH, status=VerificationStatus.UNSUPPORTED)]
    )
    decision = decide(report, confidence=0.99, input_flags=[])
    assert decision.status is ResponseStatus.ABSTAIN
    assert decision.reason is AbstentionReason.UNSUPPORTED_HIGH_RISK_CLAIM


def test_contradiction_abstains_even_with_high_confidence():
    report = VerificationReport(contradictions=[Contradiction(id="x1", claim_id="c1")])
    decision = decide(report, confidence=0.99, input_flags=[])
    assert decision.status is ResponseStatus.ABSTAIN
    assert decision.reason is AbstentionReason.CONFLICTING_EVIDENCE


def test_prompt_injection_flag_overrides_everything():
    report = VerificationReport()
    flags = [SafetyFlag(code="prompt_injection", severity=RiskLevel.HIGH)]
    decision = decide(report, confidence=1.0, input_flags=flags)
    assert decision.status is ResponseStatus.ABSTAIN
    assert decision.reason is AbstentionReason.POLICY_RESTRICTION


def test_priority_order_policy_beats_unsupported_high_risk_claim():
    report = VerificationReport(
        claims=[Claim(id="c1", text="x", risk=RiskLevel.CRITICAL, status=VerificationStatus.CONTRADICTED)]
    )
    flags = [SafetyFlag(code="prompt_injection")]
    decision = decide(report, confidence=0.99, input_flags=flags)
    assert decision.reason is AbstentionReason.POLICY_RESTRICTION


def test_supported_claim_ratio_is_carried_through():
    report = VerificationReport(
        claims=[
            Claim(id="c1", text="x", status=VerificationStatus.SUPPORTED),
            Claim(id="c2", text="y", status=VerificationStatus.UNSUPPORTED),
        ]
    )
    decision = decide(report, confidence=1.0, input_flags=[])
    assert decision.supported_claim_ratio == 0.5
