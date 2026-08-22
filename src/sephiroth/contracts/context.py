"""Typed per-consultation context, and what each agent is allowed to see of it.

Today every specialist receives the exact same raw `dict` — a `RadiologyAgent`
gets `lab_results` it never reads, a `LabAgent` gets `image_path` it never
opens. `RunContext` names the fields that actually flow through the system
today; `AgentCapability.context_fields` (`capability.py`) is what lets an
agent declare which of them it needs, enforced by
`src/sephiroth/context/views.py::context_for_agent`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunContext(BaseModel):
    """The full context dict, typed. Constructed once per consultation;
    agents see a filtered projection of it, never the raw dict directly."""

    model_config = ConfigDict(extra="forbid")

    medications: list[str] = Field(default_factory=list)
    lab_results: dict[str, Any] = Field(default_factory=dict)
    image_path: str | None = None
    conditions: list[str] = Field(default_factory=list)
    history: str = Field(default="", description="Free-text past medical history, not conversational turns.")
    language: str = Field(
        default="en",
        description=(
            'UI language code the client is set to ("en" or "es"); '
            "agents are asked to answer in this language."
        ),
    )
    recent_consultations: list[str] = Field(
        default_factory=list,
        description=(
            "Short digests of this patient's most recent prior consultations "
            "(query + answer excerpt), computed on the fly from the "
            "Consultation table — never persisted on RunContext itself."
        ),
    )

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "RunContext":
        """Builds a `RunContext` from the legacy raw context dict, ignoring
        unknown keys (the dict has historically accepted arbitrary keys;
        the contract only knows about the ones actually consumed today)."""
        raw = raw or {}
        known = {name for name in cls.model_fields}
        return cls(**{k: v for k, v in raw.items() if k in known and v is not None})


__all__ = ["RunContext"]
