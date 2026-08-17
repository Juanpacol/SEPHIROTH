"""The runtime's shared state.

Replaces both the vestigial `intelligence.agents.AgentState` dataclass (which
was referenced nowhere) and the ephemeral LangGraph `WorkflowState` TypedDict
(which lived only for the duration of one `ainvoke` and was never validated).

`extra="forbid"` is the point: the TypedDict silently accepted a typo'd key and
dropped it. Here it raises.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .claims import CitationReport, Claim, Contradiction
from .enums import LifecycleState, RiskLevel
from .evidence import Citation, EvidenceRecord
from .plan import ExecutionPlan
from .results import AgentResult, Failure, RecoveryAction, ToolCall
from .safety import AbstentionDecision, SafetyFlag
from .task import TaskAnalysis
from .trace import Span


class RunState(BaseModel):
    """Everything one consultation accumulates, start to finish.

    Serializable by construction so it can be checkpointed later without
    readopting a workflow framework — a checkpointer becomes a Protocol plus a
    table, not a dependency.
    """

    model_config = ConfigDict(extra="forbid")

    # --- request ---
    trace_id: str
    request: str
    patient_id: str = ""
    patient_context: dict[str, Any] = Field(default_factory=dict)

    # --- analysis and planning ---
    task: TaskAnalysis | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    plan: ExecutionPlan | None = None
    selected_agents: list[str] = Field(default_factory=list)
    lifecycle: dict[str, LifecycleState] = Field(
        default_factory=dict, description="step or agent id -> current lifecycle state"
    )

    # --- execution ---
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    # --- evidence and verification ---
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    citation_report: CitationReport = Field(default_factory=CitationReport)

    # --- safety ---
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    abstention: AbstentionDecision | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- failures and recovery ---
    failures: list[Failure] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
    recovery_actions: list[RecoveryAction] = Field(default_factory=list)

    # --- output ---
    final_answer: str = ""

    # --- observability (SPEC-006) ---
    spans: list[Span] = Field(
        default_factory=list,
        description="Recorded by sephiroth.telemetry.traced_span; empty when tracing is disabled.",
    )

    @property
    def agent_outputs(self) -> dict[str, str]:
        """The legacy `{agent_name: content}` projection.

        `_persist` and the SSE `final` event are both shaped around this, so it
        stays available as a derived view rather than duplicated state.
        """
        return {name: result.content for name, result in self.agent_results.items()}

    @property
    def agents_involved(self) -> list[str]:
        """Sorted, matching the wire contract — the frontend renders in order
        and the value is persisted to `consultations.agents`."""
        return sorted(self.agent_results)


__all__ = ["RunState"]
