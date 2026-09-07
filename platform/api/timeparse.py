"""One rule for datetimes crossing the API boundary.

Every column in this schema is naive UTC. That is the convention, it is
consistent, and it is not what changes here — what changes is how a value gets
there.

**A naive datetime in a request is refused.** Not assumed to be UTC, and above
all not passed to `astimezone`, which interprets a naive value as the *server's*
local time: on a machine in Bogotá, `2026-09-07T09:00` becomes 14:00 UTC, and
the caller who meant 09:00 UTC has silently lost five hours.

Five scheduling endpoints already did this correctly, inline, five times.
`create_exception` did not do it at all, which is how a surgeon's blocked
morning ended up stored at the wrong hour (SPEC-027 §2). One function, called
everywhere, is what makes "everywhere" checkable — `test_datetime_contract.py`
walks every request model and fails on a `datetime` field nobody guards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException


def require_aware(value: datetime, field: str) -> datetime:
    """An aware datetime, converted to naive UTC for storage. Otherwise 422.

    The error names the field because a request body with three datetimes in it
    gives a caller nothing to act on otherwise.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field} must include a timezone offset (for example "
                f"2026-09-07T09:00:00-05:00). A time without one is ambiguous, "
                f"and guessing it would store the wrong hour."
            ),
        )
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def optional_aware(value: Optional[datetime], field: str) -> Optional[datetime]:
    """`require_aware` for a field that may be absent."""
    return None if value is None else require_aware(value, field)


__all__ = ["optional_aware", "require_aware"]
