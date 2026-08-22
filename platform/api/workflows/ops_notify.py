"""Operator-facing tick health notifications (Slack). Deliberately
separate from `channels.py`'s `NotificationChannel` -- that protocol
delivers text to a `User` row and persists a `Notification`; this is a
metric summary with no user, no persistence, and must never carry
patient content. Mixing the two would blur "text for a patient" with
"metric for an operator", exactly the line PHI safety depends on.

**Redaction is a contract, not a convention** -- same posture as
`sephiroth.contracts.trace.ALLOWED_SPAN_ATTRIBUTES` (SPEC-005): an
allow-list, because a deny-list fails open. `patient_id` is
deliberately absent; `workflow_id`/`step_id` are enough to look a
step up in the database without ever putting a patient identifier in
a third-party service's servers.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol

import httpx

from core.config import settings

#: Field names permitted in an ops notification payload. Anything else is
#: dropped rather than sent -- see module docstring.
ALLOWED_OPS_FIELDS = frozenset(
    {
        "tick_id",
        "claimed",
        "succeeded",
        "failed",
        "skipped",
        "remaining",
        "events_dispatched",
        "workflow_id",
        "step_id",
        "step_type",
    }
)


class OpsNotifier(Protocol):
    async def notify(self, fields: Dict[str, Any]) -> bool:
        """Returns True if the notification was actually sent."""
        ...


def _format_text(fields: Dict[str, Any]) -> str:
    filtered = {k: v for k, v in fields.items() if k in ALLOWED_OPS_FIELDS}
    disallowed = set(fields) - ALLOWED_OPS_FIELDS
    if disallowed:
        raise ValueError(f"ops notification fields are allow-listed; drop or rename: {sorted(disallowed)}")
    parts = [f"{k}={v}" for k, v in filtered.items()]
    return "tick " + " ".join(parts)


class SlackNotifier:
    """Fire-and-forget POST to a Slack incoming webhook -- same posture
    as `intelligence/mcp/rag_server.py`'s outbound call: a short-lived
    client, a numeric timeout, and a swallowed failure. A dead webhook
    must never affect the tick it's reporting on."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def notify(self, fields: Dict[str, Any]) -> bool:
        text = _format_text(fields)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(self._webhook_url, json={"text": text})
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False


class NullNotifier:
    async def notify(self, fields: Dict[str, Any]) -> bool:
        return False


def get_ops_notifier() -> OpsNotifier:
    if settings.slack_webhook_url:
        return SlackNotifier(settings.slack_webhook_url)
    return NullNotifier()


__all__ = ["OpsNotifier", "SlackNotifier", "NullNotifier", "get_ops_notifier", "ALLOWED_OPS_FIELDS"]
