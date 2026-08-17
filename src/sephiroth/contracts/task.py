"""Task analysis — the structured metadata the planner consumes.

The analyzer classifies an incoming request; it never executes agents. Keeping
those concerns apart is what lets the planner be swapped (static → LLM-driven)
without touching classification.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import Complexity, RiskLevel, TaskType


class TaskAnalysis(BaseModel):
    """Structured classification of a request, produced before planning."""

    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    complexity: Complexity = Complexity.SIMPLE
    risk: RiskLevel = RiskLevel.LOW
    requires_evidence: bool = True
    requires_verification: bool = False
    candidate_agents: list[str] = Field(
        default_factory=list,
        description="AgentCapability.id references the planner may draw from",
    )
    signals: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Boolean input signals derived from the request context "
            "(has_image, has_lab_results, has_medications). The static planner "
            "routes on these alone, reproducing legacy `route_specialists`."
        ),
    )
    rationale: str = ""


__all__ = ["TaskAnalysis"]
