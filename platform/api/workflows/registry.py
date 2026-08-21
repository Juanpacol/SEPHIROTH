"""Step-type registry -- the `TOOL_CAPABILITIES` (`src/sephiroth/tools/servers.py`)
/ `_ACTION_TEMPLATES` (`src/sephiroth/telemetry/explain.py`) pattern applied
to workflow steps: a literal dict mapping a `step_type` string to a frozen
spec, so `engine.py` never branches on step type by name.
"""

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


def _build_step_types() -> Dict[str, StepTypeSpec]:
    from . import alert_escalation, handlers

    return {
        "alert_refresh": StepTypeSpec(
            step_type="alert_refresh",
            handler=handlers.alert_refresh,
            max_attempts=3,
            max_lateness_seconds=None,  # internal housekeeping -- always worth catching up
            timeout_seconds=10.0,
            reads_phi=False,  # reads lab/med data already visible to any clinician; not a per-patient PHI read event
        ),
        alert_escalation.STEP_TYPE: StepTypeSpec(
            step_type=alert_escalation.STEP_TYPE,
            handler=alert_escalation.escalate_if_unresolved,
            max_attempts=3,
            max_lateness_seconds=None,  # an overdue escalation still matters -- catch up forever
            timeout_seconds=10.0,
            reads_phi=True,  # notifies clinicians about a specific patient's alert
        ),
    }


STEP_TYPES: Dict[str, StepTypeSpec] = _build_step_types()

__all__ = ["StepContext", "StepResult", "StepTypeSpec", "StepHandler", "STEP_TYPES"]
