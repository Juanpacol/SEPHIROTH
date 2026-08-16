"""Normalized evidence records.

Evidence is append-only: once written to the run state it is never mutated, and
claims reference it by id. That invariant is what makes a trace replayable —
you can always reconstruct which passage a claim was judged against.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import RetrievalMethod, SourceType, SupportRelationship


class Citation(BaseModel):
    """A source reference as it appears to the reader.

    `label` is the human-facing form the model is instructed to emit —
    `[ADA Standards of Care in Diabetes, 2024]` or `[PMID:12345]` — and is what
    citation auditing matches against tool output.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    locator: str | None = None
    url: str | None = None


class EvidenceRecord(BaseModel):
    """One retrieved passage, normalized across retrieval strategies."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    source_type: SourceType
    retrieval_method: RetrievalMethod
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    citation: Citation
    originating_agent: str
    timestamp: datetime
    support_relationship: SupportRelationship = SupportRelationship.NEUTRAL
    content: str = ""


__all__ = ["Citation", "EvidenceRecord"]
