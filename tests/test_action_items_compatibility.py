"""`/api/dashboard/action-items` must not change shape when it changes source.

The dashboard and its `DashboardActionItem` type predate the task table. This
phase re-points that endpoint at `tasks` behind `enable_task_inbox`, and the
whole value of doing it behind a flag is lost if the two paths disagree — a
frontend that works with the flag off and breaks with it on is a rollback that
does not roll back.

So the assertion here is not "the new path works". It is "both paths answer the
same question the same way, over the same fixture".

Verifies AC-018-15, AC-018-16 (docs/specs/SPEC-018-unified-tasks.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.services.task_derivation import sync_derived_tasks
from core.config import settings
from core.db import get_session
from data.schemas import ImagingStudy, LabResult, Patient, PendingAction

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 12, 0, 0)


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"compat-{uuid4().hex[:8]}@example.org",
            "name": "Dra. Compat",
            "password": "password123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def clinical_fixture(db_session):
    """One patient carrying three findable conditions at once."""
    patient = Patient(
        id="PCOM1",
        name="Ana Ruiz",
        age=54,
        sex="F",
        medical_record_number="MRN-PCOM1",
        medications=["warfarina", "aspirina"],
    )
    db_session.add(patient)
    db_session.add(
        LabResult(
            patient_id="PCOM1",
            test_name="Potasio",
            value="6.8",
            unit="mmol/L",
            taken_at=NOW - timedelta(hours=2),
            is_abnormal=True,
            is_critical=True,
        )
    )
    db_session.add(
        ImagingStudy(
            id=str(uuid4()),
            patient_id="PCOM1",
            modality="CT",
            body_part="tórax",
            severity="critical",
            study_date=NOW - timedelta(days=1),
        )
    )
    db_session.add(
        PendingAction(
            id="PA-COM1",
            patient_id="PCOM1",
            action_type="followup_check",
            draft_text="¿Cómo seguís?",
        )
    )
    await db_session.commit()
    return patient


def _comparable(payload: dict) -> set:
    """The identity of an item, ignoring the fields the task path adds."""
    added = {"task_id", "status", "due_at"}
    return {
        tuple(sorted((k, str(v)) for k, v in item.items() if k not in added)) for item in payload["items"]
    }


async def test_both_paths_return_the_same_items_for_the_same_fixture(
    client, clinical_fixture, db_session, monkeypatch
):
    headers = await _clinician(client)

    monkeypatch.setattr(settings, "enable_task_inbox", False)
    derived = (await client.get("/api/dashboard/action-items", headers=headers)).json()

    # Populate the table the way the tick would, then read the same endpoint.
    await sync_derived_tasks(db_session, NOW)
    await db_session.commit()
    monkeypatch.setattr(settings, "enable_task_inbox", True)
    from_tasks = (await client.get("/api/dashboard/action-items", headers=headers)).json()

    assert derived["total_count"] == from_tasks["total_count"]
    assert _comparable(derived) == _comparable(from_tasks)


async def test_the_task_backed_path_adds_an_id_so_a_row_can_be_acted_on(
    client, clinical_fixture, db_session, monkeypatch
):
    """The whole point of the change: a dashboard row stops being a sentence
    and becomes something with a handle."""
    headers = await _clinician(client)
    await sync_derived_tasks(db_session, NOW)
    await db_session.commit()
    monkeypatch.setattr(settings, "enable_task_inbox", True)

    body = (await client.get("/api/dashboard/action-items", headers=headers)).json()

    assert body["items"], "fixture should produce work"
    assert all(item["task_id"] for item in body["items"])
    # And the id is real: it resolves through the task API.
    first = body["items"][0]["task_id"]
    assert (await client.get(f"/api/tasks/{first}", headers=headers)).status_code == 200


async def test_severity_ordering_survives_the_change(client, clinical_fixture, db_session, monkeypatch):
    headers = await _clinician(client)
    await sync_derived_tasks(db_session, NOW)
    await db_session.commit()
    monkeypatch.setattr(settings, "enable_task_inbox", True)

    body = (await client.get("/api/dashboard/action-items", headers=headers)).json()

    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severities = [rank[i["severity"]] for i in body["items"]]
    assert severities == sorted(severities)


async def test_bootstrap_keeps_its_three_top_level_keys(client, clinical_fixture, db_session, monkeypatch):
    """`/bootstrap` is the frontend's single first-paint call; adding or losing
    a key there is a broken dashboard, not a degraded one."""
    headers = await _clinician(client)
    await sync_derived_tasks(db_session, NOW)
    await db_session.commit()

    for flag in (False, True):
        monkeypatch.setattr(settings, "enable_task_inbox", flag)
        body = (await client.get("/api/dashboard/bootstrap", headers=headers)).json()
        assert set(body) == {"stats", "agenda", "action_items"}
        assert set(body["action_items"]) == {"items", "total_count"}
