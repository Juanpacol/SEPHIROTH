"""Safety flags and abstention.

Abstention is the capability the current system most conspicuously lacks:
`citation_guard.sanitize()` silently replaces a fabricated citation with
`[unverified — removed]` and returns the answer anyway. Nothing causes the
runtime to decline to answer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import AbstentionReason, ResponseStatus, RiskLevel


class SafetyFlag(BaseModel):
    """One policy or risk finding raised against a candidate answer."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: RiskLevel = RiskLevel.LOW
    message: str = ""
    claim_id: str | None = None


class AbstentionDecision(BaseModel):
    """Whether to answer, hedge, or decline — and on what evidence.

    `reason` is required when abstaining and forbidden otherwise, so a trace can
    never record a decline without saying why.
    """

    model_config = ConfigDict(extra="forbid")

    status: ResponseStatus = ResponseStatus.ANSWER
    reason: AbstentionReason | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supported_claim_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    message: str = ""

    def model_post_init(self, _context: object) -> None:
        if self.status is ResponseStatus.ABSTAIN and self.reason is None:
            raise ValueError("an abstention must carry a reason")
        if self.status is ResponseStatus.ANSWER and self.reason is not None:
            raise ValueError(f"a non-abstaining response must not carry reason={self.reason!r}")


__all__ = ["AbstentionDecision", "SafetyFlag"]
