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

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from data.schemas import Alert, Appointment, ImagingStudy, Patient, Workflow, WorkflowStep
from intelligence.mcp.drug_safety_server import find_interactions
from sephiroth.workflows.events import WorkflowEvent

_SEVERITY_EMOJI = {"critical": "🚨", "high": "⚠️", "medium": "🟡", "low": "ℹ️"}

#: Categorical vocabulary only -- used to build genuinely bilingual lines
#: for structured fields (severity words, follow-up check names). Free
#: text authored elsewhere (`Alert.title`/`.detail`, an AI imaging
#: `finding_summary`, a drug interaction's `effect`/`recommendation`) is
#: NOT run through this: translating arbitrary free text deterministically
#: isn't possible, and an LLM call here would break SPEC-009's "no LLM
#: inside the tick, ever" (this digest is built on every tick, via
#: `daily_digest.py`). That free text is shown once, as authored, under
#: both language headers rather than faked as translated.
_SEVERITY_ES = {"critical": "crítica", "high": "alta", "medium": "media", "low": "baja"}
_INTERACTION_SEVERITY_ES = {"major": "mayor", "moderate": "moderada", "minor": "menor"}
_CHECK_LABEL = {"day3": ("día 3", "day 3"), "day7": ("día 7", "day 7"), "day30": ("día 30", "day 30")}

#: Slack's own semantic palette (danger/warning/good/info) -- the color
#: bar on the attachment, independent of any emoji in the text itself.
_SEVERITY_COLOR = {"critical": "#E01E5A", "high": "#ECB22E", "medium": "#2EB67D", "low": "#36C5F0"}
_DIGEST_COLOR_OK = "#2EB67D"
_DIGEST_COLOR_ATTENTION = "#ECB22E"


async def _post_blocks(fallback_text: str, blocks: List[Dict[str, Any]], color: str) -> bool:
    """Posts one message with `blocks` at the message's TOP LEVEL, not
    nested inside `attachments` (the previous shape) -- Slack's own
    guidance is that attachment content can be wrapped, truncated, or
    hidden behind a "show more" toggle by clients
    (https://api.slack.com/messaging/composing/layouts), which is exactly
    what surfaced once the bilingual digest grew past a couple of
    categories: the English section rendered collapsed/cut off. `color`
    still renders as a colored accent bar via a content-free attachment
    (Slack's supported pattern for a bar decoupled from the real body).
    `fallback_text` is Slack's required `text` field -- shown in
    notification previews and to clients that don't render blocks."""
    if not settings.clinical_slack_webhook_url:
        return False
    payload = {"text": fallback_text, "blocks": blocks, "attachments": [{"color": color}]}
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
#
#    Bilingual, action-first: each line names a patient and what the
#    clinician needs to do, not a raw metric -- and appears once in
#    Spanish and once in English so either reader can act on it directly
#    without a mental translation step.
# ---------------------------------------------------------------------------

_MAX_DIGEST_ITEMS_PER_CATEGORY = 5


@dataclass
class ActionItem:
    """One digest line, pre-rendered in both languages. `text_es`/`text_en`
    only genuinely differ for fields this module controls (severity words,
    follow-up check names, static labels) -- see the module-level note by
    `_SEVERITY_ES` on why free text (alert titles, AI imaging findings,
    drug-interaction descriptions) is shown once, unmodified, under both
    language headers rather than machine-translated."""

    emoji: str
    text_es: str
    text_en: str


def _category_block(
    header_es: str, header_en: str, items: List[ActionItem], lang: str, empty: str
) -> Dict[str, Any]:
    header = header_es if lang == "es" else header_en
    if not items:
        return _text_section(f"*{header}*\n{empty}")
    lines = [f"{item.emoji} {item.text_es if lang == 'es' else item.text_en}" for item in items]
    return _text_section(f"*{header}*\n" + "\n".join(lines))


async def _alert_action_items(session: AsyncSession, alerts: List[Alert]) -> List[ActionItem]:
    items = []
    for alert in alerts[:_MAX_DIGEST_ITEMS_PER_CATEGORY]:
        patient = await session.get(Patient, alert.patient_id)
        name_es = patient.name if patient else "Paciente sin identificar"
        name_en = patient.name if patient else "Unknown patient"
        emoji = _SEVERITY_EMOJI.get(alert.severity, "🔔")
        detail = f" — {alert.detail}" if alert.detail else ""
        severity_es = _SEVERITY_ES.get(alert.severity, alert.severity)
        items.append(
            ActionItem(
                emoji,
                f"*{name_es}* — {alert.title}{detail} _(severidad {severity_es})_",
                f"*{name_en}* — {alert.title}{detail} _(severity: {alert.severity})_",
            )
        )
    return items


async def _interaction_action_items(session: AsyncSession) -> List[ActionItem]:
    """Deterministic drug-pair scan (`find_interactions`, no LLM) across
    every active patient with 2+ medications on file -- new signal the
    digest didn't surface before; a real interaction sat invisible until
    someone opened that one patient's chart."""
    patients = (await session.scalars(select(Patient).where(Patient.status == "active"))).all()
    items: List[ActionItem] = []
    for patient in patients:
        if len(patient.medications) < 2:
            continue
        for hit in find_interactions(patient.medications):
            if len(items) >= _MAX_DIGEST_ITEMS_PER_CATEGORY:
                return items
            drug_a, drug_b = hit["pair"]
            severity = hit.get("severity", "")
            items.append(
                ActionItem(
                    "💊",
                    f"*{patient.name}* — {drug_a} + {drug_b}: interacción "
                    f"{_INTERACTION_SEVERITY_ES.get(severity, severity)}. Revisar tratamiento.",
                    f"*{patient.name}* — {drug_a} + {drug_b}: {severity} interaction. Review treatment.",
                )
            )
    return items


async def _imaging_action_items(session: AsyncSession) -> tuple[List[ActionItem], int]:
    studies = (
        await session.scalars(
            select(ImagingStudy)
            .where(ImagingStudy.severity.in_(("critical", "review")))
            .order_by(ImagingStudy.severity.desc(), ImagingStudy.study_date.desc())
        )
    ).all()
    items = []
    for study in studies[:_MAX_DIGEST_ITEMS_PER_CATEGORY]:
        patient = await session.get(Patient, study.patient_id)
        name_es = patient.name if patient else "Paciente sin identificar"
        name_en = patient.name if patient else "Unknown patient"
        critical = study.severity == "critical"
        emoji = "🚨" if critical else "🩻"
        label_es = "hallazgo crítico" if critical else "pendiente de revisión"
        label_en = "critical finding" if critical else "needs review"
        items.append(
            ActionItem(
                emoji,
                f"*{name_es}* — {study.modality.upper()} ({study.body_part}): {label_es}",
                f"*{name_en}* — {study.modality.upper()} ({study.body_part}): {label_en}",
            )
        )
    return items, len(studies)


async def _overdue_followup_action_items(
    session: AsyncSession, now: datetime
) -> tuple[List[ActionItem], int]:
    """A day-3/7/30 check (`patient_followup.py`) still pending past its
    due date -- the tick will keep trying it up to `MAX_LATENESS`, but a
    clinician seeing it here can act sooner than that grace period."""
    rows = (
        await session.execute(
            select(WorkflowStep, Workflow)
            .join(Workflow, WorkflowStep.workflow_id == Workflow.id)
            .where(
                WorkflowStep.step_type == "followup_check_due",
                WorkflowStep.status == "pending",
                WorkflowStep.due_at < now,
                Workflow.followup_plan_id.isnot(None),
            )
            .order_by(WorkflowStep.due_at)
        )
    ).all()
    items = []
    for step, workflow in rows[:_MAX_DIGEST_ITEMS_PER_CATEGORY]:
        patient = await session.get(Patient, workflow.patient_id)
        name_es = patient.name if patient else "Paciente sin identificar"
        name_en = patient.name if patient else "Unknown patient"
        check_es, check_en = _CHECK_LABEL.get(step.step_key, (step.step_key, step.step_key))
        days_late = max((now - step.due_at).days, 0)
        items.append(
            ActionItem(
                "📅",
                f"*{name_es}* — seguimiento {check_es} vencido ({days_late}d de retraso), no enviado",
                f"*{name_en}* — {check_en} follow-up overdue ({days_late}d late), not yet sent",
            )
        )
    return items, len(rows)


async def build_and_send_digest(session: AsyncSession) -> bool:
    now = datetime.now()
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

    alert_items = await _alert_action_items(session, open_alerts)
    interaction_items = await _interaction_action_items(session)
    imaging_items, imaging_total = await _imaging_action_items(session)
    followup_items, followup_total = await _overdue_followup_action_items(session, now)

    total_action_items = len(open_alerts) + len(interaction_items) + imaging_total + followup_total

    blocks: List[Dict[str, Any]] = [
        _header("📋 Resumen Clínico Diario · Daily Clinical Digest"),
        _context(date.today().strftime("%A, %B %-d, %Y")),
    ]
    for lang, flag_label in (("es", "🇪🇸 Español"), ("en", "🇬🇧 English")):
        blocks.append({"type": "divider"})
        blocks.append(_text_section(f"*{flag_label}*"))
        blocks.append(
            _category_block(
                "🚨 Alertas activas",
                "🚨 Active alerts",
                alert_items,
                lang,
                "Sin alertas activas." if lang == "es" else "No active alerts.",
            )
        )
        blocks.append(
            _category_block(
                "💊 Interacciones de medicamentos",
                "💊 Drug interactions",
                interaction_items,
                lang,
                "No se detectaron interacciones." if lang == "es" else "No interactions detected.",
            )
        )
        blocks.append(
            _category_block(
                "🩻 Imágenes por revisar",
                "🩻 Imaging needing review",
                imaging_items,
                lang,
                "Nada pendiente." if lang == "es" else "Nothing pending.",
            )
        )
        blocks.append(
            _category_block(
                "📅 Seguimientos vencidos",
                "📅 Overdue follow-ups",
                followup_items,
                lang,
                "Ninguno vencido." if lang == "es" else "None overdue.",
            )
        )
    blocks.append({"type": "divider"})
    blocks.append(_fields_section([("Citas hoy · Appointments today", str(appointments_today))]))

    color = _DIGEST_COLOR_ATTENTION if total_action_items else _DIGEST_COLOR_OK
    fallback = (
        f"Daily digest {date.today().isoformat()}: {total_action_items} action item(s), "
        f"{appointments_today} appointments today"
    )
    return await _post_blocks(fallback, blocks, color)


__all__ = [
    "on_clinical_alert",
    "notify_consultation_needs_review",
    "build_and_send_digest",
]
