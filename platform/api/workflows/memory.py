"""Operational memory (SPEC-015) -- quiet hours, reminder lead time,
contact preference. `ALLOWED_KEYS` is the enforcement point: never add a
clinical fact here (conditions, medications, lab values, risk flags all
already have an authoritative home -- `Patient`, `Consultation`, etc.,
per CLAUDE.md decision #16). `set_memory` raises on anything else.

No automation phase reads this yet -- Phase 10's reminder handler does
not check quiet hours. Wiring that in requires a `StepResult` outcome
meaning "not done, try again later" that the engine (SPEC-009) doesn't
have today; adding one is real work, not something to bolt on here
just to make this table feel used. This phase ships the store and its
API, proven standalone.
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import AutomationMemory

VALID_SCOPES = ("clinic", "user", "patient")

#: key -> one-line description of the expected value shape. Enforced by
#: membership only (not a JSON Schema) -- the set is small and hand-reviewed,
#: same "literal dict, not a generality" call as TOOL_CAPABILITIES.
ALLOWED_KEYS: Dict[str, str] = {
    "quiet_hours": "{'start': 'HH:MM', 'end': 'HH:MM'} local time -- no reminder sent inside this window",
    "reminder_lead_hours": "int -- override the default 24h appointment reminder lead time",
    "contact_preference": "'in_app' -- the only channel that exists (Phase 8); reserved for 'email'/'sms'",
}


class InvalidMemoryKey(ValueError):
    pass


def _validate(scope: str, key: str) -> None:
    if scope not in VALID_SCOPES:
        raise InvalidMemoryKey(f"scope must be one of {VALID_SCOPES}, got {scope!r}")
    if key not in ALLOWED_KEYS:
        raise InvalidMemoryKey(
            f"key {key!r} is not in the allowed operational-memory key set: {sorted(ALLOWED_KEYS)}"
        )


async def get_memory(session: AsyncSession, scope: str, scope_id: str, key: str, default: Any = None) -> Any:
    _validate(scope, key)
    row = await session.scalar(
        select(AutomationMemory).where(
            AutomationMemory.scope == scope,
            AutomationMemory.scope_id == scope_id,
            AutomationMemory.key == key,
        )
    )
    return row.value if row is not None else default


async def set_memory(
    session: AsyncSession, scope: str, scope_id: str, key: str, value: Any
) -> AutomationMemory:
    """Upsert. Does not commit -- caller's transaction."""
    _validate(scope, key)
    row = await session.scalar(
        select(AutomationMemory).where(
            AutomationMemory.scope == scope,
            AutomationMemory.scope_id == scope_id,
            AutomationMemory.key == key,
        )
    )
    if row is None:
        row = AutomationMemory(id=str(uuid4()), scope=scope, scope_id=scope_id, key=key, value=value)
        session.add(row)
    else:
        row.value = value
    return row


__all__ = ["VALID_SCOPES", "ALLOWED_KEYS", "InvalidMemoryKey", "get_memory", "set_memory"]
