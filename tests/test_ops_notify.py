"""Slack tick-health notifications. Two things matter here: PHI can never
reach the payload (`ALLOWED_OPS_FIELDS` is an allow-list, same posture as
`sephiroth.contracts.trace.ALLOWED_SPAN_ATTRIBUTES`), and a dead webhook
can never turn a healthy tick into a 500 -- `/internal/tick` fires the
notifier only after `run_tick` has already returned its summary."""

from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.workflows import registry as registry_module
from api.workflows.engine import TickSummary
from api.workflows.ops_notify import NullNotifier, SlackNotifier, get_ops_notifier
from api.workflows.registry import StepContext, StepResult, StepTypeSpec
from core.config import settings
from core.db import get_session
from data.schemas import Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 22, 12, 0, 0)


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _patient_workflow_step(session, step_type, *, status="pending"):
    patient = Patient(id="POPS1", name="Ops Patient", age=40, sex="F", medical_record_number="PT-POPS1")
    session.add(patient)
    wf = Workflow(id=str(uuid4()), definition_key="test_def", patient_id=patient.id, status="active")
    session.add(wf)
    step = WorkflowStep(
        id=str(uuid4()),
        workflow_id=wf.id,
        step_key=str(uuid4())[:8],
        step_type=step_type,
        status=status,
        due_at=NOW,
        run_after=NOW,
    )
    session.add(step)
    await session.commit()
    return wf, step


async def test_patient_id_is_rejected_not_dropped():
    """A caller passing patient_id is a bug -- it must be loud, not
    silently swallowed like an unknown key would be elsewhere."""
    from api.workflows.ops_notify import _format_text

    with pytest.raises(ValueError, match="patient_id"):
        _format_text({"tick_id": "t1", "patient_id": "P001"})


async def test_format_text_only_uses_allowed_fields():
    from api.workflows.ops_notify import _format_text

    text = _format_text({"tick_id": "t1", "claimed": 3, "failed": 1})

    assert "t1" in text
    assert "claimed=3" in text
    assert "failed=1" in text


async def test_null_notifier_when_no_webhook_configured():
    assert settings.slack_webhook_url is None  # guaranteed by the autouse fixture
    notifier = get_ops_notifier()
    assert isinstance(notifier, NullNotifier)
    assert await notifier.notify({"tick_id": "t1"}) is False


async def test_slack_notifier_selected_when_webhook_configured(monkeypatch):
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/services/fake")
    notifier = get_ops_notifier()
    assert isinstance(notifier, SlackNotifier)


async def test_empty_tick_does_not_notify(client, monkeypatch):
    """No steps due -> succeeded == failed == 0 -> the silence guard in
    internal.py must not even construct a notifier."""
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/services/fake")

    called = {"n": 0}

    async def _spy_notify(self, fields):
        called["n"] += 1
        return True

    monkeypatch.setattr(SlackNotifier, "notify", _spy_notify)

    res = await client.post(
        "/internal/tick", headers={"X-Internal-Token": "a-real-secret-value-thats-long-enough"}
    )

    assert res.status_code == 200
    assert res.json()["claimed"] == 0
    assert called["n"] == 0


async def test_tick_with_failure_notifies_with_workflow_and_step_id_never_patient_id(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/services/fake")

    wf, step = await _patient_workflow_step(db_session, "no_such_step_type")

    captured = {}

    async def _spy_notify(self, fields):
        captured.update(fields)
        return True

    monkeypatch.setattr(SlackNotifier, "notify", _spy_notify)

    res = await client.post(
        "/internal/tick", headers={"X-Internal-Token": "a-real-secret-value-thats-long-enough"}
    )

    assert res.status_code == 200
    assert res.json()["failed"] == 1
    assert captured["step_id"] == step.id
    assert captured["workflow_id"] == wf.id
    assert "patient_id" not in captured
    assert "POPS1" not in str(captured)


async def test_slack_outage_does_not_fail_the_tick(client, db_session, monkeypatch):
    """The central property: SlackNotifier swallows httpx errors, so a
    dead webhook must never turn a healthy tick into a 500. No real
    network call -- httpx's client is monkeypatched to raise the same
    error class a real outage would surface."""
    monkeypatch.setattr(settings, "enable_workflow_engine", True)
    monkeypatch.setattr(settings, "internal_tick_token", "a-real-secret-value-thats-long-enough")
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/services/fake")

    real_post = httpx.AsyncClient.post

    async def _raises_only_for_webhook(self, url, *args, **kwargs):
        if url == "https://hooks.slack.com/services/fake":
            raise httpx.ConnectError("simulated outage")
        return await real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _raises_only_for_webhook)

    async def _always_succeeds(ctx: StepContext) -> StepResult:
        return StepResult(outcome="succeeded", data={})

    monkeypatch.setitem(
        registry_module.STEP_TYPES,
        "ops_notify_test_ok",
        StepTypeSpec(step_type="ops_notify_test_ok", handler=_always_succeeds),
    )
    await _patient_workflow_step(db_session, "ops_notify_test_ok")

    res = await client.post(
        "/internal/tick", headers={"X-Internal-Token": "a-real-secret-value-thats-long-enough"}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["succeeded"] == 1


async def test_tick_summary_failed_steps_not_in_to_dict():
    """The HTTP response shape to the cron caller never changes --
    failed_steps is internal to the router's ops-notify wiring only."""
    summary = TickSummary(tick_id="t1", failed=1, failed_steps=[{"step_id": "s1"}])
    assert "failed_steps" not in summary.to_dict()
