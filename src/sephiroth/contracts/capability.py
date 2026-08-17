"""Agent and tool capability metadata — the registry's source of truth.

Today agent identity is a Python class with two class attributes and a
hardcoded import in the router. Turning agents into *data* is what makes
capability-based routing possible: the planner asks "who can do
medication_interaction?" instead of naming a class.

`docs/02-agents/registry.md` carries the YAML that loads into these models.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import RiskLevel


class RiskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: RiskLevel = RiskLevel.LOW
    requires_human_review: bool = False


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parallelizable: bool = True
    requires_evidence: bool = False
    requires_verification: bool = False
    timeout_seconds: float = Field(default=60.0, gt=0)


class AgentCapability(BaseModel):
    """What an agent can do, what it may call, and how risky it is.

    `id` is the wire-facing display identity (hyphenated, e.g. `drug-safety`);
    `node_name` is the internal scheduling identity (underscored, e.g.
    `drug_safety`). Both exist today implicitly and the frontend normalises
    between them — see `docs/00-migration-charter.md` §2.1. Carrying both
    explicitly is what eventually lets that normalisation be removed.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    node_name: str
    name: str
    description: str = ""
    role_prompt: str = Field(
        default="",
        description=(
            "The agent's system-prompt fragment, moved byte-for-byte from the "
            "pre-Phase-3 hardcoded classes. Substrings of this string are what "
            "tests/conftest.py::FakeLLMClient._script_for matches against — "
            "rewording it silently degrades those tests to their default "
            "script (see docs/00-migration-charter.md, the FakeLLMClient trap)."
        ),
    )
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    risk: RiskSpec = Field(default_factory=RiskSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    model_hint: str | None = None
    context_fields: list[str] = Field(
        default_factory=list,
        description=(
            "Which sephiroth.contracts.context.RunContext field names this "
            "agent actually needs. Empty list (the default) means every "
            "field — backward compatible with agents that don't declare a "
            "narrower view. See src/sephiroth/context/views.py."
        ),
    )


class ToolDescriptor(BaseModel):
    """Capability-based tool access control.

    `allowed_agents` is enforced server-side by the tool runtime. The legacy
    registry enforced nothing at execution time — the whitelist only filtered
    which schemas the model was shown, so a model naming an out-of-scope tool
    would still have it executed.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    risk: RiskSpec = Field(default_factory=RiskSpec)
    allowed_agents: list[str] = Field(default_factory=list)
    mcp_server: str | None = None


__all__ = ["AgentCapability", "ExecutionSpec", "RiskSpec", "ToolDescriptor"]
