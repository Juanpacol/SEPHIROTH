"""How long a piece of clinical work has before it is late.

This table used to live in `platform/api/workflows/alert_escalation.py` as
`ESCALATION_WINDOW_BY_SEVERITY`, where it answered one question: when should an
unreviewed alert be escalated. A task's `due_at` is the same question asked by
a different caller, so the table moves here and both read it. Two copies of a
clinical deadline that drift apart is exactly the kind of bug nobody notices
until the wrong thing is overdue.

`alert_escalation` still imports the old name from this module, so no call site
changed and the existing tests keep asserting against the same object.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

#: Time from raised to due, by severity. One tier -- there is no escalation
#: ladder yet, and inventing one here would be building a policy engine for a
#: policy that has a single input.
SLA_WINDOW_BY_SEVERITY: Dict[str, timedelta] = {
    "critical": timedelta(hours=1),
    "high": timedelta(hours=4),
    "medium": timedelta(hours=24),
    "low": timedelta(hours=72),
}

DEFAULT_SLA_WINDOW = timedelta(hours=24)

#: Categories whose own deadline beats the severity table. An approval that
#: expires in 14 days is not "due in an hour" because it happens to be
#: critical -- the source's deadline is the real one, and inventing a tighter
#: one just manufactures overdue work nobody can act on.
CATEGORY_USES_SOURCE_DEADLINE = frozenset({"approval"})


def sla_window(severity: str) -> timedelta:
    return SLA_WINDOW_BY_SEVERITY.get(severity, DEFAULT_SLA_WINDOW)


def due_at_for(
    severity: str,
    created_at: datetime,
    *,
    category: str = "",
    source_deadline: Optional[datetime] = None,
) -> datetime:
    """When this work is late.

    A source deadline wins for the categories that have one, and only when it
    is actually later than now -- an already-expired deadline would otherwise
    create a task born overdue.
    """
    if category in CATEGORY_USES_SOURCE_DEADLINE and source_deadline is not None:
        if source_deadline > created_at:
            return source_deadline
    return created_at + sla_window(severity)


__all__ = [
    "SLA_WINDOW_BY_SEVERITY",
    "DEFAULT_SLA_WINDOW",
    "CATEGORY_USES_SOURCE_DEADLINE",
    "sla_window",
    "due_at_for",
]
