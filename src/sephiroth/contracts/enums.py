"""Closed vocabularies shared across the runtime.

Every enum here is a contract: its members appear in persisted traces, in
`docs/specs/contracts/*.schema.json`, and in evaluation output. Adding a member
is a MINOR spec bump; removing or renaming one is MAJOR and needs an ADR
(SPEC-000 §6.3).

`StrEnum` rather than `Enum` so that `model_dump(mode="json")` yields plain
strings and a trace round-trips through JSON without custom encoders.
"""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    """Clinical risk, used both for routing decisions and safety gating."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(StrEnum):
    """What kind of clinical question the runtime was handed."""

    DIAGNOSTIC = "diagnostic"
    THERAPEUTIC = "therapeutic"
    INTERPRETIVE = "interpretive"
    INFORMATIONAL = "informational"
    TRIAGE = "triage"


class Complexity(StrEnum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class LifecycleState(StrEnum):
    """Agent lifecycle. Transitions are normative in SPEC-003 §6.3; the
    canonical picture is D2 (`docs/09-diagrams/architecture/D2-agent-lifecycle.md`)."""

    REGISTERED = "registered"
    SELECTED = "selected"
    PLANNED = "planned"
    EXECUTING = "executing"
    WAITING = "waiting"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"
    ABSTAINED = "abstained"


class VerificationStatus(StrEnum):
    """Claim-level verdict.

    Today's `citation_guard` is binary (verified / fabricated) and operates on
    citation *labels*. This five-state vocabulary operates on claim *content*
    against retrieved evidence, which is the Phase 4 capability.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class SupportRelationship(StrEnum):
    """How one evidence record relates to the claim it was retrieved for."""

    SUPPORTS = "supports"
    REFUTES = "refutes"
    NEUTRAL = "neutral"


class SourceType(StrEnum):
    GUIDELINE = "guideline"
    LITERATURE = "literature"
    PATIENT_RECORD = "patient_record"
    TOOL_OUTPUT = "tool_output"
    MODEL_PRIOR = "model_prior"


class RetrievalMethod(StrEnum):
    """How a passage reached the agent — needed to attribute retrieval quality
    to a strategy during evaluation."""

    LEXICAL = "lexical"
    DENSE = "dense"
    HYBRID = "hybrid"
    TOOL = "tool"
    DIRECT_CONTEXT = "direct_context"


class FailureCategory(StrEnum):
    """Failure taxonomy. Every `Failure` carries one, so failures can be
    aggregated by component across an evaluation run."""

    PLANNING = "planning"
    ROUTING = "routing"
    AGENT = "agent"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    EVIDENCE = "evidence"
    VERIFICATION = "verification"
    SAFETY = "safety"
    MODEL = "model"
    RECOVERY = "recovery"


class RecoveryActionType(StrEnum):
    RETRY = "retry"
    FALLBACK = "fallback"
    REPLAN = "replan"
    ABSTAIN = "abstain"


class AbstentionReason(StrEnum):
    """Why the runtime declined to answer confidently. Persisted so abstention
    precision can be measured per reason."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    UNSUPPORTED_HIGH_RISK_CLAIM = "unsupported_high_risk_claim"
    TOOL_FAILURE = "tool_failure"
    MODEL_UNCERTAINTY = "model_uncertainty"
    POLICY_RESTRICTION = "policy_restriction"
    OUT_OF_SCOPE = "out_of_scope"


class ResponseStatus(StrEnum):
    ANSWER = "answer"
    PARTIAL = "partial"
    ABSTAIN = "abstain"


class SpanKind(StrEnum):
    """Instrumentation seams, frozen from Phase 1 onward (SPEC-005)."""

    RUN = "run"
    PLAN = "plan"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    VERIFY = "verify"


__all__ = [
    "AbstentionReason",
    "Complexity",
    "FailureCategory",
    "LifecycleState",
    "RecoveryActionType",
    "ResponseStatus",
    "RetrievalMethod",
    "RiskLevel",
    "SourceType",
    "SpanKind",
    "SupportRelationship",
    "TaskType",
    "VerificationStatus",
]
