"""Daily clinical digest -- checked on every tick, sent at most once per
calendar day. Tracked via `automation_memory` (scope='clinic'), not a
`Workflow` row: `Workflow.patient_id` is a real, NOT NULL foreign key to
`patients` -- every existing workflow is anchored to one patient's
lifecycle -- and a clinic-wide digest has no single patient to anchor to.
Forcing a sentinel patient id would violate that foreign key (or silently
mislead a reader into thinking the digest is about one patient); a
dedicated `automation_memory` key is the honest fit -- it is exactly
"operational timing state", the table's stated purpose.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from . import clinical_notify
from .memory import get_memory, set_memory

_SCOPE = "clinic"
_SCOPE_ID = "default"  # single-tenant app -- see memory.py::_validate_scope_id
_KEY = "last_digest_sent_date"


async def maybe_send_daily_digest(session: AsyncSession) -> bool:
    """Sends the digest and records today's date if it hasn't already
    gone out today. Returns True if it just sent. Safe to call on every
    tick -- a day with no webhook configured still records the date
    (build_and_send_digest no-ops silently), so flipping the webhook on
    mid-day doesn't cause a burst of backfilled digests."""
    today_str = date.today().isoformat()
    last_sent = await get_memory(session, _SCOPE, _SCOPE_ID, _KEY)
    if last_sent == today_str:
        return False

    await clinical_notify.build_and_send_digest(session)
    await set_memory(session, _SCOPE, _SCOPE_ID, _KEY, today_str)
    await session.commit()
    return True


__all__ = ["maybe_send_daily_digest"]
