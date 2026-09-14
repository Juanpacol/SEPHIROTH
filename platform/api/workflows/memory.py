"""Operational memory (SPEC-015) -- quiet hours, reminder lead time,
contact preference. `ALLOWED_KEYS` is the enforcement point: never add a
clinical fact here (conditions, medications, lab values, risk flags all
already have an authoritative home -- `Patient`, `Consultation`, etc.,
per CLAUDE.md decision #16). `set_memory` raises on anything else --
and, per the security review, that used to mean the *key* only: the
*value* went into the JSON column verbatim, so "never a clinical fact
here" was a comment, not a control. `_KEY_SPECS` closes that: each
allowed key also has a value shape it must satisfy.

No automation phase reads this yet -- Phase 10's reminder handler does
not check quiet hours. Wiring that in requires a `StepResult` outcome
meaning "not done, try again later" that the engine (SPEC-009) doesn't
have today; adding one is real work, not something to bolt on here
just to make this table feel used. This phase ships the store and its
API, proven standalone.
"""

from __future__ import annotations

import re
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import AutomationMemory, Patient, User

VALID_SCOPES = ("clinic", "user", "patient")

_TIME_RE = re.compile(r"^[0-2][0-9]:[0-5][0-9]$")


def _validate_quiet_hours(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise InvalidMemoryKey("quiet_hours must be exactly {'start': 'HH:MM', 'end': 'HH:MM'}")
    for k in ("start", "end"):
        if not isinstance(value[k], str) or not _TIME_RE.match(value[k]):
            raise InvalidMemoryKey(f"quiet_hours.{k} must be 'HH:MM' (00-23:00-59), got {value[k]!r}")


def _validate_reminder_lead_hours(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 168):
        raise InvalidMemoryKey("reminder_lead_hours must be an int between 1 and 168 (one week)")


def _validate_contact_preference(value: Any) -> None:
    if value != "in_app":
        raise InvalidMemoryKey("contact_preference must be 'in_app' -- the only channel that exists")


#: key -> (one-line description, value validator). A hand-reviewed literal
#: dict, not a JSON Schema -- same "literal dict, not a generality" call as
#: TOOL_CAPABILITIES. Every key's *value* is validated, not just its name:
#: an allow-listed key with an unchecked value is not actually enforced.
_KEY_SPECS: Dict[str, tuple] = {
    "quiet_hours": (
        "{'start': 'HH:MM', 'end': 'HH:MM'} local time -- no reminder sent inside this window",
        _validate_quiet_hours,
    ),
    "reminder_lead_hours": (
        "int (1-168) -- override the default 24h appointment reminder lead time",
        _validate_reminder_lead_hours,
    ),
    "contact_preference": (
        "'in_app' -- the only channel that exists (Phase 8); reserved for 'email'/'sms'",
        _validate_contact_preference,
    ),
}

#: Public, description-only view -- what `GET /api/automation-memory/keys` returns.
ALLOWED_KEYS: Dict[str, str] = {key: desc for key, (desc, _validator) in _KEY_SPECS.items()}


class InvalidMemoryKey(ValueError):
    pass


def _validate_key(scope: str, key: str) -> None:
    if scope not in VALID_SCOPES:
        raise InvalidMemoryKey(f"scope must be one of {VALID_SCOPES}, got {scope!r}")
    if key not in _KEY_SPECS:
        raise InvalidMemoryKey(
            f"key {key!r} is not in the allowed operational-memory key set: {sorted(_KEY_SPECS)}"
        )


async def _validate_scope_id(session: AsyncSession, scope: str, scope_id: str) -> None:
    """`clinic` has no backing table (this app is single-tenant, per
    CLAUDE.md) -- any id is accepted there. `user`/`patient` must name a
    real row, or an authenticated clinician could write unbounded rows
    under ids that reference nothing (storage growth with no operator
    ever able to look the row up by its subject)."""
    if scope == "user":
        exists = await session.scalar(select(User.id).where(User.id == scope_id))
    elif scope == "patient":
        exists = await session.scalar(select(Patient.id).where(Patient.id == scope_id))
    else:
        return
    if exists is None:
        raise InvalidMemoryKey(f"no {scope} exists with id {scope_id!r}")


async def get_memory(session: AsyncSession, scope: str, scope_id: str, key: str, default: Any = None) -> Any:
    _validate_key(scope, key)
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
    """Upsert. Does not commit -- caller's transaction. Raises
    `InvalidMemoryKey` for an unknown scope/key, a value that doesn't
    match that key's required shape, or a `scope_id` that names no real
    user/patient."""
    _validate_key(scope, key)
    _KEY_SPECS[key][1](value)
    await _validate_scope_id(session, scope, scope_id)

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
