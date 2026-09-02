"""Operator-facing tick health notifications (Slack). Deliberately
separate from `channels.py`'s `NotificationChannel` -- that protocol
delivers text to a `User` row and persists a `Notification`; this is a
metric summary with no user, no persistence, and must never carry
patient content. Mixing the two would blur "text for a patient" with
"metric for an operator", exactly the line PHI safety depends on.

Also deliberately separate from `clinical_notify.py` (a different
webhook, `SLACK_WEBHOOK_URL` vs `CLINICAL_SLACK_WEBHOOK_URL`) -- that one
is for clinicians and needs patient-identifying clinical signal; this one
is for engineers and must never carry it. Same **structured, not plain
text** posture as that module, though: Slack Block Kit wrapped in a
color-barred attachment, not a single mrkdwn string, so a run of failures
reads as a scannable card instead of a paragraph of `key=value` pairs.

**Redaction is a contract, not a convention** -- same posture as
`sephiroth.contracts.trace.ALLOWED_SPAN_ATTRIBUTES` (SPEC-005): an
allow-list, because a deny-list fails open. `patient_id` is
deliberately absent; `workflow_id`/`step_id` are enough to look a
step up in the database without ever putting a patient identifier in
a third-party service's servers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple

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
        "failed_steps",
        "failed_steps_more",
    }
)

#: Keys permitted inside each `failed_steps` entry -- same allow-list
#: discipline as `ALLOWED_OPS_FIELDS` one level down, so a nested field
#: (e.g. an accidental `patient_id`) can't slip through unnoticed.
ALLOWED_FAILED_STEP_FIELDS = frozenset({"step_id", "workflow_id", "step_type"})

_COLOR_OK = "#2EB67D"
_COLOR_PARTIAL = "#ECB22E"
_COLOR_FAILED = "#E01E5A"


class OpsNotifier(Protocol):
    async def notify(self, fields: Dict[str, Any]) -> bool:
        """Returns True if the notification was actually sent."""
        ...


def _header(text: str) -> Dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _context(text: str) -> Dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _fields_section(pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
    return {
        "type": "section",
        "fields": [{"type": "mrkdwn", "text": f"*{label}:*\n{value}"} for label, value in pairs],
    }


def _format_blocks(fields: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str]:
    """Renders a tick summary as Slack Block Kit -- a status-emoji
    header, a 2x3 field grid for the counters, and (only when there were
    failures) one line per failed step instead of three parallel
    comma-joined columns the reader has to align by eye. Returns
    (fallback_text, blocks, color) for `_post_blocks`."""
    disallowed = set(fields) - ALLOWED_OPS_FIELDS
    if disallowed:
        raise ValueError(f"ops notification fields are allow-listed; drop or rename: {sorted(disallowed)}")

    for step in fields.get("failed_steps", []):
        bad = set(step) - ALLOWED_FAILED_STEP_FIELDS
        if bad:
            raise ValueError(f"failed_steps entries are allow-listed; drop or rename: {sorted(bad)}")

    tick_id = fields.get("tick_id", "unknown")
    claimed = fields.get("claimed", 0)
    succeeded = fields.get("succeeded", 0)
    failed = fields.get("failed", 0)
    skipped = fields.get("skipped", 0)
    remaining = fields.get("remaining", 0)
    events_dispatched = fields.get("events_dispatched", 0)

    if failed == 0:
        emoji, color, status_word = "✅", _COLOR_OK, "OK"
    elif succeeded == 0 and claimed > 0:
        emoji, color, status_word = "🔴", _COLOR_FAILED, "Failed"
    else:
        emoji, color, status_word = "⚠️", _COLOR_PARTIAL, "Partial"

    blocks: List[Dict[str, Any]] = [
        _header(f"{emoji} Workflow Tick — {status_word}"),
        _context(f"`{tick_id}`"),
        _fields_section(
            [
                ("Claimed", str(claimed)),
                ("Succeeded", str(succeeded)),
                ("Failed", str(failed)),
                ("Skipped", str(skipped)),
                ("Remaining", str(remaining)),
                ("Events dispatched", str(events_dispatched)),
            ]
        ),
    ]

    failed_steps = fields.get("failed_steps", [])
    if failed_steps:
        blocks.append({"type": "divider"})
        lines = [
            f"• `{step['step_type']}` — step `{step['step_id']}` (workflow `{step['workflow_id']}`)"
            for step in failed_steps
        ]
        more = fields.get("failed_steps_more")
        if more:
            lines.append(f"…and {more} more")
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Failed steps:*\n" + "\n".join(lines)}}
        )

    fallback = f"{emoji} Workflow tick {tick_id}: claimed {claimed}, succeeded {succeeded}, failed {failed}"
    return fallback, blocks, color


class SlackNotifier:
    """Fire-and-forget POST to a Slack incoming webhook -- same posture
    as `intelligence/mcp/rag_server.py`'s outbound call: a short-lived
    client, a numeric timeout, and a swallowed failure. A dead webhook
    must never affect the tick it's reporting on."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def notify(self, fields: Dict[str, Any]) -> bool:
        fallback_text, blocks, color = _format_blocks(fields)
        payload = {"text": fallback_text, "attachments": [{"color": color, "blocks": blocks}]}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(self._webhook_url, json=payload)
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
