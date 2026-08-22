"""Per-agent and per-tool execution records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import FailureCategory, RecoveryActionType


class ToolCall(BaseModel):
    """One tool invocation.

    `result` is retained deliberately: citation auditing harvests allowed
    citations from tool results, so dropping it would make every genuine
    citation look fabricated. The streaming `agent_completed` event omits it to
    keep the wire small, but `final` and the persisted record keep it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    tool: str
    agent: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    ok: bool = True
    latency_ms: int = Field(default=0, ge=0)
    timestamp: datetime | None = None


class AgentResult(BaseModel):
    """What one agent produced during one plan step.

    `prompt_tokens`/`completion_tokens` (SPEC-016, closing SPEC-006 NG-2)
    come straight from `ChatResult` -- real provider usage, not a
    placeholder -- for any client that reports it (`GeminiClient`,
    `GroqClient`); 0 for a test double that doesn't."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    step_id: str = ""
    content: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    rounds: int = Field(default=0, ge=0)


class Failure(BaseModel):
    """A classified failure. Every failure carries a taxonomy category so an
    evaluation run can attribute failures to components."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: FailureCategory
    component: str
    message: str = ""
    step_id: str | None = None
    attempt: int = Field(default=1, ge=1)
    timestamp: datetime | None = None


class RecoveryAction(BaseModel):
    """What the runtime did about a failure, and whether it worked.

    `succeeded is None` means the action was taken but its outcome is not yet
    known — distinct from `False`, which means recovery was attempted and
    failed. The difference matters when computing recovery success rate.
    """

    model_config = ConfigDict(extra="forbid")

    failure_id: str
    action: RecoveryActionType
    detail: str = ""
    succeeded: bool | None = None


__all__ = ["AgentResult", "Failure", "RecoveryAction", "ToolCall"]
