"""Execution traces — the observability contract.

A trace is the immutable, replayable record of one run. It is what makes
behaviour reproducible for evaluation, so it carries model versions alongside
results: the same benchmark against a different model must be distinguishable
after the fact.

**Redaction is a contract, not a convention.** `Span.attributes` is an
allow-list of scalar metadata. Clinical content never enters a span — see
SPEC-005.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .claims import CitationReport, Claim, Contradiction, VerificationReport
from .enums import RiskLevel, SpanKind
from .evidence import EvidenceRecord
from .plan import ExecutionPlan
from .results import AgentResult, Failure, RecoveryAction, ToolCall
from .safety import AbstentionDecision, SafetyFlag
from .task import TaskAnalysis

#: Span attribute keys permitted by the redaction contract. Anything else is
#: dropped rather than recorded — a deny-list would fail open.
ALLOWED_SPAN_ATTRIBUTES = frozenset(
    {
        "agent",
        "tool_name",
        "model",
        "provider",
        "rounds",
        "prompt_tokens",
        "completion_tokens",
        "step_id",
        "attempt",
        "ok",
        "status",
    }
)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LlmCall(BaseModel):
    """One call to a model provider, as it actually happened.

    Exists because the run-level `model_versions` could only say what the
    client was *configured* with: behind a fallback client that is always the
    primary, so a run answered by the secondary still read as the primary.
    One record per call, because a single consultation makes several (the
    answer, the verification, sometimes the routing) and each can fall back on
    its own.

    **Metadata only.** Same redaction contract as `Span.attributes`: no prompt,
    no answer, no tool arguments, and `error` is a short code, never the
    provider's own text.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["chat", "generate_json", "describe_image", "describe_image_stream"]
    provider: str
    model: str
    ok: bool = True
    #: A reason code (`rate_limited`, `no_api_key`, ...) when `ok` is False.
    error: str = ""
    #: True when this call served a request an earlier provider could not.
    fallback: bool = False
    #: Who failed first and why, only when `fallback` is True.
    fallback_from: str = ""
    fallback_reason: str = ""
    duration_ms: int = Field(default=0, ge=0)
    #: 0 where the provider reports no usage (`generate_json` does not yet).
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class Span(BaseModel):
    """One instrumented interval. Spans nest via `parent_id` to form a tree
    rooted at the run."""

    model_config = ConfigDict(extra="forbid")

    id: str
    trace_id: str
    parent_id: str | None = None
    kind: SpanKind
    name: str
    started_at: datetime
    duration_ms: int = Field(default=0, ge=0)
    ok: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, _context: object) -> None:
        disallowed = set(self.attributes) - ALLOWED_SPAN_ATTRIBUTES
        if disallowed:
            raise ValueError(f"span attributes are allow-listed; drop or rename: {sorted(disallowed)}")


class ExecutionTrace(BaseModel):
    """The complete, replayable record of one consultation."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    created_at: datetime
    request: str
    patient_id: str = ""

    task: TaskAnalysis | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    plan: ExecutionPlan | None = None
    selected_agents: list[str] = Field(default_factory=list)

    agent_calls: list[AgentResult] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)

    evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    verification: VerificationReport | None = None
    citation_report: CitationReport = Field(default_factory=CitationReport)

    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    abstention: AbstentionDecision | None = None

    failures: list[Failure] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
    recovery_actions: list[RecoveryAction] = Field(default_factory=list)

    latency_ms: int = Field(default=0, ge=0)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = Field(default=0.0, ge=0.0)

    #: Provider and model identifiers active for this run. Reproducibility
    #: depends on it: the same benchmark on a different model must not look
    #: like the same result. When `llm_calls` is present this is the provider
    #: and model of the call that produced the answer, not just the configured
    #: primary.
    model_versions: dict[str, str] = Field(default_factory=dict)

    #: Every model call the run made, in order. Empty for a run with no model
    #: call (the fast path) and for traces persisted before this field existed.
    llm_calls: list[LlmCall] = Field(default_factory=list)

    final_answer: str = ""


__all__ = ["ALLOWED_SPAN_ATTRIBUTES", "ExecutionTrace", "LlmCall", "Span", "TokenUsage"]
