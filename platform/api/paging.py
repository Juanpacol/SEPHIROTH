"""A cap on a list endpoint that returns a bare array.

Several endpoints predate the paginated shape SPEC-018 introduced
(`{items, total_count, ...}`), and their callers destructure the array
directly. Changing their body shape to add paging would break every one of
them for a problem that is about *size*, not about shape.

So the cap goes on, and the count goes in a header. The client that does not
read it behaves exactly as before on any realistic clinic; the client that
wants to know it was truncated can find out, and the endpoint stops growing
without bound as a clinic accumulates history.

The alternative was leaving them unbounded, which works right up until the
afternoon a three-year-old clinic serialises every alert it has ever raised
into one response.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from fastapi import Response
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

#: Header carrying the number of rows that matched, before the cap.
TOTAL_HEADER = "X-Total-Count"


async def capped(
    session: AsyncSession,
    statement: Select,
    response: Optional[Response],
    *,
    limit: int,
    offset: int = 0,
) -> Sequence[Any]:
    """Run `statement` bounded, and report the true total in a header.

    The count reuses the caller's filters by wrapping the statement as a
    subquery, so the two can never disagree about what "total" means -- a
    hand-written second query is a filter somebody forgets to add.
    """
    if response is not None:
        total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        response.headers[TOTAL_HEADER] = str(int(total or 0))

    return (await session.scalars(statement.limit(limit).offset(offset))).all()


__all__ = ["TOTAL_HEADER", "capped"]
