"""Per-agent context views — F-034.

Every specialist has historically received the exact same raw context
dict, whether or not it reads all of it. `context_for_agent` projects
`RunContext` down to only the fields an `AgentCapability` declares via
`context_fields`.

Rollout (`docs/00-migration-charter.md` §9 requires permissive-then-enforcing
for this specific change): `log_filtered_fields` runs first, in permissive
mode, recording what *would* be dropped per agent without changing
behavior; `context_for_agent` is the enforcing projection, switched on only
after an eval run showed zero agents depending on a field outside their
declared `context_fields`. See `docs/specs/SPEC-005-context-engine.md` §7.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from sephiroth.contracts import AgentCapability, RunContext

logger = logging.getLogger("sephiroth.context.views")


def context_for_agent(
    capability: AgentCapability, ctx: RunContext, *, answering: bool = False
) -> Dict[str, Any]:
    """Projects `ctx` down to the fields `capability.context_fields` names.

    An empty `context_fields` (the default) means "every field" — backward
    compatible with any capability that hasn't declared a narrower view.

    `answering=True` marks the agent that produces the consultation's final
    answer. In multi-agent mode that is always the coordinator, whose empty
    `context_fields` already grants it everything — including the
    `recent_consultations` digest the router injects (ADR-011: memory is
    scoped to the answering agent, never fanned out to every specialist).
    In single-agent mode a specialist answers directly, so it needs that
    same digest or per-patient memory would silently vanish. Only
    `recent_consultations` is added — the rest of the specialist's narrow
    view is unchanged, so this widens memory access without widening
    clinical-data access.
    """
    full = ctx.model_dump(mode="python")
    if not capability.context_fields:
        return full
    fields = set(capability.context_fields)
    if answering:
        fields.add("recent_consultations")
    projected = {name: value for name, value in full.items() if name in fields}
    projected["language"] = full[
        "language"
    ]  # response-language directive, not patient data — always passes through
    return projected


def log_filtered_fields(capability: AgentCapability, ctx: RunContext) -> None:
    """Permissive-mode instrumentation: logs which fields would be dropped
    for this agent, without changing what it actually receives. Used during
    the observation window before `context_for_agent` is wired in as the
    real projection."""
    if not capability.context_fields:
        return
    full = ctx.model_dump(mode="python")
    dropped = [name for name, value in full.items() if name not in capability.context_fields and value]
    if dropped:
        logger.info("context_fields_would_drop agent=%s fields=%s", capability.id, dropped)


__all__ = ["context_for_agent", "log_filtered_fields"]
