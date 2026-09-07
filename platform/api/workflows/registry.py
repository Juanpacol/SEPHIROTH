"""Step-type registry -- the `TOOL_CAPABILITIES` (`src/sephiroth/tools/servers.py`)
/ `_ACTION_TEMPLATES` (`src/sephiroth/telemetry/explain.py`) pattern applied
to workflow steps: a literal dict mapping a `step_type` string to a frozen
spec, so `engine.py` never branches on step type by name.

`STEP_TYPES` starts empty. Each definition module (`handlers.py`,
`alert_escalation.py`, `appointment_reminder.py`, ...) imports
`StepContext`/`StepResult`/`register_step_type` from here and calls
`register_step_type(...)` for each of its step types at the bottom of
its own file. This module never imports them back -- `definitions.py`
is the one place that imports every definition module (for the
self-registration side effect), so which module gets imported "first"
in any given test or startup path can never create a cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Workflow, WorkflowStep

from .channels import NotificationChannel


@dataclass(frozen=True)
class StepContext:
    session: AsyncSession
    step: WorkflowStep
    workflow: Workflow
    now: datetime
    channel: NotificationChannel


@dataclass(frozen=True)
class StepResult:
    outcome: Literal["succeeded", "skipped", "superseded"]
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


StepHandler = Callable[[StepContext], Awaitable[StepResult]]


@dataclass(frozen=True)
class StepTypeSpec:
    step_type: str
    handler: StepHandler
    max_attempts: int = 3
    max_lateness_seconds: int | None = None
    timeout_seconds: float = 5.0
    reads_phi: bool = True


STEP_TYPES: Dict[str, StepTypeSpec] = {}


def register_step_type(spec: StepTypeSpec) -> None:
    """Idempotent by construction -- re-registering the same
    `step_type` just overwrites with an identical spec, since each
    definition module is only ever imported once per process."""
    STEP_TYPES[spec.step_type] = spec


__all__ = ["StepContext", "StepResult", "StepTypeSpec", "StepHandler", "STEP_TYPES", "register_step_type"]
