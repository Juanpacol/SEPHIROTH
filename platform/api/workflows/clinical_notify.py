"""Clinician-facing Slack notifications -- deliberately a separate module
and webhook from `ops_notify.py`. That channel is engineering/ops: workflow
health, PHI excluded by contract (an allow-list, patient_id absent on
purpose). This one exists BECAUSE a clinician needs patient-identifying
clinical signal to act on -- a new critical alert, an AI answer flagged
for review, a daily digest. Putting both kinds of message in one channel
is exactly the "a doctor sees a tick_id and infers nothing" problem this
module fixes by not existing in the same place.

**Structured, not plain text.** Every message is Slack Block Kit
(`header`/`section`/`context` blocks) wrapped in a color-barred
`attachment`, not a single mrkdwn string -- fields render as an aligned
grid, the color bar carries severity at a glance, and a plain-text
`text` fallback still ships for notification previews and screen
readers, per Slack's own guidance.

**Privacy posture.** This app's whole clinical-text pipeline already
leaves the machine for a third party (the Gemini API -- see the privacy
notice in CLAUDE.md and README). Posting a patient's name to a Slack
webhook is not a new category of exposure in that context, just an
additional destination, and it is required for the message to mean
anything to a clinician. This posture only holds for the same reason the
rest of the app's does: synthetic/de-identified data, not a real
deployment with real patients. Do not point `CLINICAL_SLACK_WEBHOOK_URL`
at a real clinic's data without re-deriving this from scratch (BAA,
patient consent, retention policy -- none of which Slack's free tier
gives you).

Every function here is fire-and-forget, same posture as `SlackNotifier`
in `ops_notify.py`: a dead webhook must never affect the request/tick
that triggered it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from data.schemas import Alert, Appointment, ImagingStudy, Patient
from sephiroth.workflows.events import WorkflowEvent

_SEVERITY_EMOJI = {"critical": "🚨", "high": "⚠️", "medium": "🟡", "low": "ℹ️"}

#: Slack's own semantic palette (danger/warning/good/info) -- the color
#: bar on the attachment, independent of any emoji in the text itself.
_SEVERITY_COLOR = {"critical": "#E01E5A", "high": "#ECB22E", "medium": "#2EB67D", "low": "#36C5F0"}
_DIGEST_COLOR_OK = "#2EB67D"
_DIGEST_COLOR_ATTENTION = "#ECB22E"


async def _post_blocks(fallback_text: str, blocks: List[Dict[str, Any]], color: str) -> bool:
    """Posts one Block-Kit message wrapped in a color-barred attachment.
    `fallback_text` is Slack's required `text` field -- shown in
    notification previews and to clients that don't render blocks."""
    if not settings.clinical_slack_webhook_url:
        return False
    payload = {"text": fallback_text, "attachments": [{"color": color, "blocks": blocks}]}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(settings.clinical_slack_webhook_url, json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def _header(text: str) -> Dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _fields_section(pairs: List[tuple[str, str]]) -> Dict[str, Any]:
    return {
        "type": "section",
        "fields": [{"type": "mrkdwn", "text": f"*{label}:*\n{value}"} for label, value in pairs],
    }


def _text_section(text: str) -> Dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> Dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


# ---------------------------------------------------------------------------
# 1) New critical alert -- subscribes to the existing CLINICAL_ALERT event
#    (src/sephiroth/safety/alerts.py already emits one per new Alert row;
#    alert_escalation.py's on_clinical_alert is the other subscriber).
# ---------------------------------------------------------------------------

#: Only these severities page a clinician in real time -- medium/low still
#: show up on the dashboard, but a Slack ping for every one would train
#: the channel to be ignored (the same alert-fatigue reasoning ADR-011's
#: context budget applies to prompts).
_NOTIFY_SEVERITIES = frozenset({"critical", "high"})


async def on_clinical_alert(session: AsyncSession, event: WorkflowEvent) -> None:
    alert = await session.get(Alert, event.entity_id)
    if alert is None or alert.severity not in _NOTIFY_SEVERITIES:
        return

    patient = await session.get(Patient, event.patient_id) if event.patient_id else None
    patient_name = patient.name if patient else "Unknown patient"
    emoji = _SEVERITY_EMOJI.get(alert.severity, "🔔")

    blocks = [
        _header(f"{emoji} New {alert.severity} alert"),
        _fields_section(
            [
                ("Patient", patient_name),
                ("Category", alert.category.replace("_", " ").title()),
            ]
        ),
        _text_section(f"*{alert.title}*\n{alert.detail}" if alert.detail else f"*{alert.title}*"),
    ]
    fallback = f"{emoji} New {alert.severity} alert — {patient_name}: {alert.title}"
    await _post_blocks(fallback, blocks, _SEVERITY_COLOR.get(alert.severity, "#616061"))


# ---------------------------------------------------------------------------
# 2) AI consultation flagged for review -- called directly from
#    platform/api/routers/agents.py right after a Consultation is
#    persisted, mirroring how internal.py calls ops_notify after run_tick.
# ---------------------------------------------------------------------------


async def notify_consultation_needs_review(
    patient_name: Optional[str], query: str, status: str, risk_level: Optional[str]
) -> bool:
    """`status` is the abstention outcome ("partial" or "abstain") --
    "answer" never calls this. A plain answer needing no review is the
    common case and must not become Slack noise."""
    who = patient_name or "no patient selected"
    query_preview = query if len(query) <= 300 else query[:297] + "…"

    if status == "abstain":
        title, emoji, color = "AI declined to answer", "🛑", "#E01E5A"
    else:
        title, emoji, color = "AI answer needs review", "⚠️", "#ECB22E"

    fields = [("Patient", who), ("Status", status.title())]
    if risk_level:
        fields.append(("Risk level", risk_level.title()))

    blocks = [
        _header(f"{emoji} {title}"),
        _fields_section(fields),
        _text_section(f"*Query:*\n_{query_preview}_"),
    ]
    fallback = f"{emoji} {title} — {who}"
    return await _post_blocks(fallback, blocks, color)


# ---------------------------------------------------------------------------
# 3) Daily digest -- checked once per tick, sent at most once per calendar
#    day (see daily_digest.py's automation_memory-backed dedupe).
# ---------------------------------------------------------------------------


async def build_and_send_digest(session: AsyncSession) -> bool:
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)

    open_alerts = (
        await session.scalars(
            select(Alert)
            .where(Alert.status == "active", Alert.severity.in_(_NOTIFY_SEVERITIES))
            .order_by(Alert.created_at.desc())
        )
    ).all()

    appointments_today = (
        await session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.status == "booked",
                Appointment.start_at >= today_start,
                Appointment.start_at < today_end,
            )
        )
        or 0
    )

    imaging_needs_review = (
        await session.scalar(
            select(func.count())
            .select_from(ImagingStudy)
            .where(ImagingStudy.severity.in_(("critical", "review")))
        )
        or 0
    )

    blocks: List[Dict[str, Any]] = [
        _header("📋 Daily Clinical Digest"),
        _context(date.today().strftime("%A, %B %-d, %Y")),
        _fields_section(
            [
                ("Open critical/high alerts", str(len(open_alerts))),
                ("Appointments today", str(appointments_today)),
                ("Imaging needing review", str(imaging_needs_review)),
            ]
        ),
    ]

    if open_alerts:
        blocks.append({"type": "divider"})
        top = open_alerts[:5]
        lines = []
        for alert in top:
            patient = await session.get(Patient, alert.patient_id)
            name = patient.name if patient else "Unknown patient"
            emoji = _SEVERITY_EMOJI.get(alert.severity, "🔔")
            lines.append(f"{emoji} *{name}* — {alert.title}")
        extra = len(open_alerts) - len(top)
        if extra > 0:
            lines.append(f"…and {extra} more")
        blocks.append(_text_section("*Top open alerts*\n" + "\n".join(lines)))

    color = _DIGEST_COLOR_ATTENTION if open_alerts or imaging_needs_review else _DIGEST_COLOR_OK
    fallback = (
        f"Daily digest {date.today().isoformat()}: {len(open_alerts)} open alerts, "
        f"{appointments_today} appointments, {imaging_needs_review} imaging to review"
    )
    return await _post_blocks(fallback, blocks, color)


__all__ = [
    "on_clinical_alert",
    "notify_consultation_needs_review",
    "build_and_send_digest",
]
