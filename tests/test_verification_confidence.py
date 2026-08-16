"""`compute_confidence` — pure-function table tests, no LLM needed.

Cheapest and most exhaustive test file in SPEC-004 (`docs/specs/SPEC-004-verification-safety.md`)
by design: the confidence formula is entirely deterministic (ADR-008).

Verifies AC-004-04.
"""

import pytest

from sephiroth.contracts import CitationReport, Claim, VerificationReport, VerificationStatus
from sephiroth.verification.confidence import compute_confidence


def _report(statuses):
    return VerificationReport(
        claims=[Claim(id=str(i), text=f"claim {i}", status=status) for i, status in enumerate(statuses)]
    )


def test_no_claims_no_fabrication_no_failures_is_full_confidence():
    report = _report([])
    citation_report = CitationReport(verified=[], fabricated=[], total_checked=0)
    assert compute_confidence(report, citation_report, tool_failures=0) == 1.0


def test_all_supported_claims_is_full_confidence():
    report = _report([VerificationStatus.SUPPORTED, VerificationStatus.SUPPORTED])
    citation_report = CitationReport(verified=["a"], fabricated=[], total_checked=1)
    assert compute_confidence(report, citation_report, tool_failures=0) == 1.0


def test_half_supported_halves_confidence():
    report = _report([VerificationStatus.SUPPORTED, VerificationStatus.UNSUPPORTED])
    citation_report = CitationReport(total_checked=0)
    assert compute_confidence(report, citation_report, tool_failures=0) == 0.5


def test_fabrication_reduces_confidence():
    report = _report([VerificationStatus.SUPPORTED])
    citation_report = CitationReport(verified=[], fabricated=["x"], total_checked=1)
    # 1.0 * (1 - 0.5*1.0) * (1 - 0) = 0.5
    assert compute_confidence(report, citation_report, tool_failures=0) == 0.5


def test_tool_failures_reduce_confidence_but_cap_at_three():
    report = _report([VerificationStatus.SUPPORTED])
    citation_report = CitationReport(total_checked=0)
    # 1.0 * 1.0 * (1 - 0.2*3/3) = 0.8
    at_cap = compute_confidence(report, citation_report, tool_failures=3)
    beyond_cap = compute_confidence(report, citation_report, tool_failures=10)
    assert at_cap == pytest.approx(0.8)
    assert beyond_cap == at_cap, "tool_failures beyond the cap must not further reduce confidence"


def test_confidence_never_negative_or_above_one():
    report = _report([VerificationStatus.UNSUPPORTED, VerificationStatus.UNSUPPORTED])
    citation_report = CitationReport(verified=[], fabricated=["a", "b"], total_checked=2)
    confidence = compute_confidence(report, citation_report, tool_failures=99)
    assert 0.0 <= confidence <= 1.0
