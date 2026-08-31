"""Clinician-facing Slack notifications (`api.workflows.clinical_notify` +
`daily_digest`). Four things matter here: messages are structured Block
Kit (not a single mrkdwn string), only critical/high alerts page
(medium/low would train the channel to be ignored), a plain "answer"
consultation never notifies (only "partial"/"abstain" do), and the daily
digest is idempotent per calendar day."""

import json
from datetime import date
from uuid import uuid4

import pytest

from api.workflows import clinical_notify
from api.workflows.daily_digest import maybe_send_daily_digest
from api.workflows.memory import get_memory
from core.config import settings
from data.schemas import Alert, ImagingStudy, Patient
from sephiroth.workflows.events import CLINICAL_ALERT, emit

pytestmark = pytest.mark.asyncio


def _dump(fallback_text, blocks):
    """Flattens a captured (fallback_text, blocks) call into one
    searchable string -- tests assert on content, not exact block shape,
    so the Block Kit structure can evolve without rewriting every test."""
    return fallback_text + "\n" + json.dumps(blocks, ensure_ascii=False)


async def _patient(session, pid="PCLN1"):
    p = Patient(id=pid, name="Clinical Notify Patient", age=61, sex="M", medical_record_number=f"PT-{pid}")
    session.add(p)
    await session.commit()
    return p


async def _alert(session, patient_id, severity="critical"):
    a = Alert(
        id=str(uuid4()),
        patient_id=patient_id,
        category="lab",
        severity=severity,
        status="active",
        title="Potassium critically high",
        detail="K+ 6.8 mmol/L",
        source="risk_engine",
    )
    session.add(a)
    await session.commit()
    return a


async def test_on_clinical_alert_notifies_for_critical(db_session, monkeypatch):
    monkeypatch.setattr(settings, "clinical_slack_webhook_url", "https://hooks.slack.com/services/fake")
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id, severity="critical")
    event = emit(db_session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
    await db_session.commit()

    captured = {}

    async def _spy(fallback_text, blocks, color):
        captured["dump"] = _dump(fallback_text, blocks)
        captured["color"] = color
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    await clinical_notify.on_clinical_alert(db_session, event)

    assert "Clinical Notify Patient" in captured["dump"]
    assert "Potassium critically high" in captured["dump"]
    assert captured["color"] == clinical_notify._SEVERITY_COLOR["critical"]


async def test_on_clinical_alert_skips_medium_and_low(db_session, monkeypatch):
    patient = await _patient(db_session)
    alert = await _alert(db_session, patient.id, severity="medium")
    event = emit(db_session, CLINICAL_ALERT, "alert", alert.id, patient_id=patient.id)
    await db_session.commit()

    called = {"n": 0}

    async def _spy(fallback_text, blocks, color):
        called["n"] += 1
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    await clinical_notify.on_clinical_alert(db_session, event)

    assert called["n"] == 0


async def test_notify_consultation_abstain_uses_declined_headline(monkeypatch):
    captured = {}

    async def _spy(fallback_text, blocks, color):
        captured["dump"] = _dump(fallback_text, blocks)
        captured["color"] = color
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    await clinical_notify.notify_consultation_needs_review(
        "Jane Doe", "should I increase the dose?", "abstain", "high"
    )

    assert "declined to answer" in captured["dump"]
    assert "Jane Doe" in captured["dump"]
    assert "High" in captured["dump"]  # risk level, title-cased
    assert captured["color"] == "#E01E5A"


async def test_notify_consultation_partial_uses_different_headline_and_color(monkeypatch):
    captured = {}

    async def _spy(fallback_text, blocks, color):
        captured["dump"] = _dump(fallback_text, blocks)
        captured["color"] = color
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    await clinical_notify.notify_consultation_needs_review(None, "query text", "partial", None)

    assert "needs review" in captured["dump"]
    assert "no patient selected" in captured["dump"]
    assert captured["color"] == "#ECB22E"


async def test_build_and_send_digest_counts_open_alerts_and_imaging(db_session, monkeypatch):
    patient = await _patient(db_session)
    await _alert(db_session, patient.id, severity="critical")
    await _alert(db_session, patient.id, severity="high")

    study = ImagingStudy(
        id=str(uuid4()),
        patient_id=patient.id,
        modality="xray",
        body_part="chest",
        study_date=date.today(),
        status="analyzed",
        severity="review",
    )
    db_session.add(study)
    await db_session.commit()

    captured = {}

    async def _spy(fallback_text, blocks, color):
        captured["dump"] = _dump(fallback_text, blocks)
        captured["color"] = color
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    sent = await clinical_notify.build_and_send_digest(db_session)

    assert sent is True
    assert "Open critical/high alerts:*\\n2" in captured["dump"]
    assert "Imaging needing review:*\\n1" in captured["dump"]
    assert "Clinical Notify Patient" in captured["dump"]
    assert captured["color"] == clinical_notify._DIGEST_COLOR_ATTENTION


async def test_build_and_send_digest_uses_ok_color_when_nothing_needs_attention(db_session, monkeypatch):
    captured = {}

    async def _spy(fallback_text, blocks, color):
        captured["color"] = color
        return True

    monkeypatch.setattr(clinical_notify, "_post_blocks", _spy)

    await clinical_notify.build_and_send_digest(db_session)

    assert captured["color"] == clinical_notify._DIGEST_COLOR_OK


async def test_maybe_send_daily_digest_is_idempotent_per_day(db_session, monkeypatch):
    calls = {"n": 0}

    async def _spy_digest(session):
        calls["n"] += 1
        return True

    monkeypatch.setattr(clinical_notify, "build_and_send_digest", _spy_digest)

    first = await maybe_send_daily_digest(db_session)
    second = await maybe_send_daily_digest(db_session)

    assert first is True
    assert second is False
    assert calls["n"] == 1

    stored = await get_memory(db_session, "clinic", "default", "last_digest_sent_date")
    assert stored == date.today().isoformat()
