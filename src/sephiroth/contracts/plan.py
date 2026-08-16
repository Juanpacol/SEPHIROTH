"""Execution plans.

Deliberately shaped for the dynamic planner from the outset: the Phase 3a
static planner emits a *degenerate* plan (every step with empty `depends_on`,
`max_iterations == 1`), so Phase 3b adds new values rather than new types.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import RecoveryActionType


class PlanStep(BaseModel):
    """One agent invocation within a plan."""

    model_config = ConfigDict(extra="forbid")

    id: str
    agent: str = Field(description="AgentCapability.id of the agent to run")
    task: str = Field(default="", description="Natural-language sub-task for the agent")
    depends_on: list[str] = Field(
        default_factory=list, description="PlanStep.id values that must complete first"
    )
    parallel: bool = True
    condition: str | None = None
    verification_required: bool = False
    recovery_path: list[RecoveryActionType] = Field(default_factory=list)
    max_attempts: int = Field(default=2, ge=1, le=10)


class ExecutionPlan(BaseModel):
    """A DAG of plan steps. `revision` increments on every REPLAN so a trace
    records how many times the runtime changed its mind."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    revision: int = Field(default=0, ge=0)
    steps: list[PlanStep] = Field(default_factory=list)
    max_iterations: int = Field(default=1, ge=1, le=25)

    @model_validator(mode="after")
    def _validate_dag(self) -> "ExecutionPlan":
        """Step ids are unique, dependencies resolve, and the graph is acyclic.

        A cycle here would hang the executor, and a dangling dependency would
        deadlock a step forever — both are cheap to reject at construction and
        expensive to debug at runtime. A hallucinated plan from an LLM planner
        is the expected source of both.
        """
        ids = [step.id for step in self.steps]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate PlanStep ids: {sorted(duplicates)}")

        known = set(ids)
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(f"step {step.id!r} depends on unknown steps: {sorted(unknown)}")
            if step.id in step.depends_on:
                raise ValueError(f"step {step.id!r} depends on itself")

        # Kahn's algorithm; whatever remains after peeling sits in a cycle.
        pending = {step.id: set(step.depends_on) for step in self.steps}
        while True:
            ready = {sid for sid, deps in pending.items() if not deps}
            if not ready:
                break
            for sid in ready:
                del pending[sid]
            for deps in pending.values():
                deps -= ready
        if pending:
            raise ValueError(f"plan contains a dependency cycle among: {sorted(pending)}")

        return self

    def execution_waves(self) -> list[list[PlanStep]]:
        """Steps grouped into dependency-ordered waves, each wave runnable
        concurrently. Within a wave, declaration order is preserved — merge
        order is observable on the wire, so it must be deterministic."""
        by_id = {step.id: step for step in self.steps}
        remaining = {step.id: set(step.depends_on) for step in self.steps}
        done: set[str] = set()
        waves: list[list[PlanStep]] = []

        while remaining:
            ready = [sid for sid in by_id if sid in remaining and not remaining[sid] - done]
            if not ready:  # pragma: no cover - the validator rejects cycles first
                raise ValueError("plan is not schedulable")
            waves.append([by_id[sid] for sid in ready])
            done.update(ready)
            for sid in ready:
                del remaining[sid]

        return waves


__all__ = ["ExecutionPlan", "PlanStep"]
