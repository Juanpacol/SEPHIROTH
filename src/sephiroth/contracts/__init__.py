"""SEPHIROTH domain contracts.

This package is a **leaf**: it imports nothing else from `sephiroth`. That is
what lets tests, schema export, and any future type generation consume the
contracts without pulling in provider SDKs or the runtime.

The models here serve double duty:

1. **Specification.** `scripts/export_contracts.py` dumps their JSON Schema to
   `docs/specs/contracts/`, and `tests/test_contracts_schema.py` fails CI if a
   model changes without the committed schema being regenerated. That is what
   makes "the spec is the source of truth" mechanically true rather than
   aspirational.
2. **Runtime validation.** The same classes validate real data at runtime
   boundaries.

See `docs/specs/SPEC-000-spec-process.md`.
"""

from .capability import AgentCapability, ExecutionSpec, RiskSpec, ToolDescriptor
from .claims import CitationReport, Claim, Contradiction, VerificationReport
from .enums import (
    AbstentionReason,
    Complexity,
    FailureCategory,
    LifecycleState,
    RecoveryActionType,
    ResponseStatus,
    RetrievalMethod,
    RiskLevel,
    SourceType,
    SpanKind,
    SupportRelationship,
    TaskType,
    VerificationStatus,
)
from .evidence import Citation, EvidenceRecord
from .plan import ExecutionPlan, PlanStep
from .results import AgentResult, Failure, RecoveryAction, ToolCall
from .safety import AbstentionDecision, SafetyFlag
from .state import RunState
from .task import TaskAnalysis
from .trace import ALLOWED_SPAN_ATTRIBUTES, ExecutionTrace, Span, TokenUsage

#: Every model whose JSON Schema is exported and drift-checked. Adding a public
#: model means adding it here — `tests/test_contracts_schema.py` asserts this
#: list covers every BaseModel subclass defined in the package.
PUBLIC_MODELS = (
    AbstentionDecision,
    AgentCapability,
    AgentResult,
    Citation,
    CitationReport,
    Claim,
    Contradiction,
    EvidenceRecord,
    ExecutionPlan,
    ExecutionSpec,
    ExecutionTrace,
    Failure,
    PlanStep,
    RecoveryAction,
    RiskSpec,
    RunState,
    SafetyFlag,
    Span,
    TaskAnalysis,
    TokenUsage,
    ToolCall,
    ToolDescriptor,
    VerificationReport,
)

__all__ = [
    "ALLOWED_SPAN_ATTRIBUTES",
    "PUBLIC_MODELS",
    "AbstentionDecision",
    "AbstentionReason",
    "AgentCapability",
    "AgentResult",
    "Citation",
    "CitationReport",
    "Claim",
    "Complexity",
    "Contradiction",
    "EvidenceRecord",
    "ExecutionPlan",
    "ExecutionSpec",
    "ExecutionTrace",
    "Failure",
    "FailureCategory",
    "LifecycleState",
    "PlanStep",
    "RecoveryAction",
    "RecoveryActionType",
    "ResponseStatus",
    "RetrievalMethod",
    "RiskLevel",
    "RiskSpec",
    "RunState",
    "SafetyFlag",
    "SourceType",
    "Span",
    "SpanKind",
    "SupportRelationship",
    "TaskAnalysis",
    "TaskType",
    "TokenUsage",
    "ToolCall",
    "ToolDescriptor",
    "VerificationReport",
    "VerificationStatus",
]
