"""Claim-level verification.

The current system audits citation *labels* against tool output — it can tell
that `[ADA, 2024]` was really retrieved, but not that the sentence attached to
it says what the guideline says. Decomposing an answer into individually
verifiable claims is what closes that gap.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import RiskLevel, VerificationStatus


class Claim(BaseModel):
    """One independently verifiable assertion extracted from an answer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    originating_agent: str = ""
    risk: RiskLevel = RiskLevel.LOW
    status: VerificationStatus = VerificationStatus.UNKNOWN
    evidence_ids: list[str] = Field(
        default_factory=list, description="EvidenceRecord.id values this claim was judged against"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class Contradiction(BaseModel):
    """A detected conflict, either between two claims or between a claim and
    the evidence retrieved for it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    claim_id: str
    conflicting_claim_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    description: str = ""


class VerificationReport(BaseModel):
    """Aggregate verdict over an answer's claims."""

    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)

    @property
    def supported_claim_ratio(self) -> float:
        """Share of claims that are fully supported.

        Drives abstention. Returns 1.0 for an answer with no claims — nothing
        unsupported was asserted, so there is nothing to abstain over.
        """
        if not self.claims:
            return 1.0
        supported = sum(1 for c in self.claims if c.status is VerificationStatus.SUPPORTED)
        return supported / len(self.claims)

    @property
    def has_unsupported_high_risk_claim(self) -> bool:
        """The single most important safety signal: a high-risk assertion the
        evidence does not back."""
        unsafe = {VerificationStatus.UNSUPPORTED, VerificationStatus.CONTRADICTED}
        high = {RiskLevel.HIGH, RiskLevel.CRITICAL}
        return any(c.status in unsafe and c.risk in high for c in self.claims)


class CitationReport(BaseModel):
    """The legacy citation-guard verdict.

    Field names are frozen: this dict is persisted to
    `consultations.citation_report` and rendered by the frontend's Citation
    Guard panel. See `docs/00-migration-charter.md` §2.2.
    """

    model_config = ConfigDict(extra="forbid")

    verified: list[str] = Field(default_factory=list)
    fabricated: list[str] = Field(default_factory=list)
    total_checked: int = 0


__all__ = ["CitationReport", "Claim", "Contradiction", "VerificationReport"]
