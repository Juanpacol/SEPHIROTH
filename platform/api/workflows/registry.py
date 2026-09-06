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
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

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
    """What a handler decided.

    `deferred` means "not now, ask me again at `retry_at`" — the outcome the
    engine lacked, and the reason `quiet_hours` and `reminder_lead_hours` were
    stored, validated and read by nothing (`memory.py`'s docstring says so).
    A deferral is not a failure and not an attempt: it does not consume a retry,
    and the step goes back to `pending` rather than to a terminal state.

    `deferred` is never *stored* as a status — it is a transient decision the
    engine translates into `pending` + a new `run_after` — which is why the
    `workflow_steps` status CHECK and `GET /api/dashboard/automation` are
    untouched by it.
    """

    outcome: Literal["succeeded", "skipped", "superseded", "deferred"]
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    #: `deferred` only: when to reconsider. The engine floors this a minute out
    #: so a handler returning "now" cannot spin the tick.
    retry_at: Optional[datetime] = None
    #: `deferred` only. A step due at 23:00 and deferred to 08:00 for quiet
    #: hours would otherwise blow past its lateness window and be silently
    #: skipped — the deferral would look like it worked and nothing would be
    #: sent. Setting this widens *this row's* budget to cover the wait, never
    #: the step type's.
    extend_lateness: bool = False


StepHandler = Callable[[StepContext], Awaitable[StepResult]]


@dataclass(frozen=True)
class StepTypeSpec:
    step_type: str
    handler: StepHandler
    max_attempts: int = 3
    max_lateness_seconds: int | None = None
    timeout_seconds: float = 5.0
    reads_phi: bool = True
    #: How many times a step of this type may defer before the engine calls it
    #: broken. `None` = unlimited, which is what a standing job like
    #: `alert_refresh` needs — it defers forever by design. For everything else
    #: a bound matters: a quiet-hours window misconfigured to cover the whole
    #: day would otherwise defer silently and forever, and a notification that
    #: never sends and never errors is the worst of both.
    max_defers: int | None = 50


STEP_TYPES: Dict[str, StepTypeSpec] = {}


def register_step_type(spec: StepTypeSpec) -> None:
    """Idempotent by construction -- re-registering the same
    `step_type` just overwrites with an identical spec, since each
    definition module is only ever imported once per process."""
    STEP_TYPES[spec.step_type] = spec


__all__ = ["StepContext", "StepResult", "StepTypeSpec", "StepHandler", "STEP_TYPES", "register_step_type"]
