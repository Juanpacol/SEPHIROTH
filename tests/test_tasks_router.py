"""`/api/tasks` — the inbox surface (SPEC-018).

Verifies AC-018-07, AC-018-08, AC-018-09, AC-018-10, AC-018-11
(docs/specs/SPEC-018-unified-tasks.md).
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.main import app
from api.services import task_service as svc
from core.db import get_session
from data.schemas import Alert, Patient, PendingAction, PhiAccessLog, Task

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email=None) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": email or f"task-{uuid4().hex[:8]}@example.org",
            "name": "Dra. Tarea",
            "password": "password123",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def seeded(db_session):
    """Three open tasks of different severities, all on one patient."""
    patient = Patient(id="PTK1", name="Ana Ruiz", age=54, sex="F", medical_record_number="PT-PTK1")
    db_session.add(patient)
    await db_session.flush()

    now = datetime(2026, 9, 6, 12, 0, 0)
    made = []
    for severity, title in [
        ("critical", "Potasio crítico"),
        ("medium", "Control sin agendar"),
        ("low", "Revisar receta"),
    ]:
        task, _ = await svc.create_task(
            db_session,
            source_type="alert",
            source_id=str(uuid4()),
            category="alert",
            severity=severity,
            title=title,
            dedupe_key=f"alert:{uuid4()}",
            patient_id=patient.id,
            now=now,
        )
        made.append(task)
    await db_session.commit()
    return made


class TestListing:
    async def test_orders_worst_first_regardless_of_category(self, client, seeded):
        headers = await _clinician(client)
        res = await client.get("/api/tasks", headers=headers)

        assert res.status_code == 200
        body = res.json()
        assert [i["severity"] for i in body["items"]] == ["critical", "medium", "low"]
        assert body["total_count"] == 3
        assert body["has_more"] is False

    async def test_paginates_with_offset_and_reports_the_full_total(self, client, seeded):
        headers = await _clinician(client)

        first = (await client.get("/api/tasks?limit=2&offset=0", headers=headers)).json()
        second = (await client.get("/api/tasks?limit=2&offset=2", headers=headers)).json()

        assert len(first["items"]) == 2 and first["has_more"] is True
        assert len(second["items"]) == 1 and second["has_more"] is False
        # total_count is the size of the result set, not of the page.
        assert first["total_count"] == second["total_count"] == 3
        assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})

    async def test_filters_by_severity_and_by_assignee(self, client, seeded):
        headers = await _clinician(client)
        await client.post(f"/api/tasks/{seeded[0].id}/claim", headers=headers)

        by_severity = (await client.get("/api/tasks?severity=low", headers=headers)).json()
        assert [i["severity"] for i in by_severity["items"]] == ["low"]

        mine = (await client.get("/api/tasks?assignee=me", headers=headers)).json()
        assert [i["id"] for i in mine["items"]] == [seeded[0].id]

        unassigned = (await client.get("/api/tasks?assignee=unassigned", headers=headers)).json()
        assert seeded[0].id not in {i["id"] for i in unassigned["items"]}

    async def test_writes_one_phi_access_row_per_patient_read(self, client, seeded, db_session):
        headers = await _clinician(client)
        await client.get("/api/tasks", headers=headers)

        rows = (
            await db_session.scalars(select(PhiAccessLog).where(PhiAccessLog.route == "/api/tasks"))
        ).all()
        # Three tasks, one patient — the log records the chart exposed, not the
        # number of rows returned.
        assert len(rows) == 1
        assert rows[0].patient_id == "PTK1"

    async def test_a_patient_cannot_read_the_clinical_inbox(self, client, db_session, seeded):
        patient = Patient(id="PTK9", name="Portal User", age=30, sex="F", medical_record_number="PT-PTK9")
        db_session.add(patient)
        await db_session.commit()
        clinician = await _clinician(client)
        invite = await client.post("/api/patients/PTK9/invites", headers=clinician)
        claimed = await client.post(
            "/api/auth/portal/claim",
            json={
                "code": invite.json()["code"],
                "email": "portal-task@example.org",
                "name": "Portal User",
                "password": "password123",
            },
        )
        patient_headers = {"Authorization": f"Bearer {claimed.json()['access_token']}"}

        res = await client.get("/api/tasks", headers=patient_headers)
        assert res.status_code == 403


class TestTransitionsOverHttp:
    async def test_claim_then_complete_walks_the_state_machine(self, client, seeded):
        headers = await _clinician(client)
        task_id = seeded[0].id

        claimed = await client.post(f"/api/tasks/{task_id}/claim", headers=headers)
        assert claimed.status_code == 200
        assert claimed.json()["status"] == "in_progress"

        done = await client.post(f"/api/tasks/{task_id}/complete", headers=headers)
        assert done.json()["status"] == "done"

    async def test_a_refused_transition_is_409_not_500(self, client, seeded):
        headers = await _clinician(client)
        task_id = seeded[0].id
        await client.post(f"/api/tasks/{task_id}/claim", headers=headers)
        await client.post(f"/api/tasks/{task_id}/complete", headers=headers)

        again = await client.post(f"/api/tasks/{task_id}/claim", headers=headers)
        assert again.status_code == 409
        assert "done" in again.json()["detail"]

    async def test_a_critical_task_refuses_to_be_snoozed(self, client, seeded):
        headers = await _clinician(client)
        until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        res = await client.post(f"/api/tasks/{seeded[0].id}/snooze", headers=headers, json={"until": until})
        assert res.status_code == 409
        assert "critical" in res.json()["detail"]

    async def test_dismiss_requires_a_reason_at_the_schema_level(self, client, seeded):
        headers = await _clinician(client)

        res = await client.post(f"/api/tasks/{seeded[2].id}/dismiss", headers=headers, json={"reason": ""})
        assert res.status_code == 422

    async def test_a_second_claim_is_refused_even_from_stale_state(self, client, seeded, db_session):
        """Two clinicians opening the inbox at the same moment must not both
        walk away believing they own the same piece of work.

        The genuine concurrent version cannot be written against this harness:
        every request shares one `AsyncSession` through the dependency
        override, and an AsyncSession used from two tasks at once raises rather
        than racing. What is asserted instead is the property that makes the
        race safe — the guard lives in the UPDATE's WHERE clause, so a claim
        issued from a *stale* read still loses. `expire` is what makes the
        second caller's view stale on purpose.
        """
        first = await _clinician(client, "race-a@example.org")
        second = await _clinician(client, "race-b@example.org")
        task_id = seeded[1].id

        won = await client.post(f"/api/tasks/{task_id}/claim", headers=first)
        assert won.status_code == 200

        db_session.expire_all()
        lost = await client.post(f"/api/tasks/{task_id}/claim", headers=second)

        assert lost.status_code == 409
        task = await db_session.get(Task, task_id)
        assert task.status == "in_progress"

    async def test_history_is_returned_with_the_task(self, client, seeded):
        headers = await _clinician(client)
        task_id = seeded[2].id
        await client.post(f"/api/tasks/{task_id}/claim", headers=headers)
        await client.post(f"/api/tasks/{task_id}/comment", headers=headers, json={"body": "llamé al lab"})

        body = (await client.get(f"/api/tasks/{task_id}", headers=headers)).json()

        assert [e["event_type"] for e in body["events"]] == ["created", "claimed", "commented"]
        assert body["events"][-1]["note"] == "llamé al lab"


class TestSourceConsistency:
    async def test_completing_an_alert_task_resolves_its_alert(self, client, db_session):
        patient = Patient(id="PTK2", name="Beto", age=61, sex="M", medical_record_number="PT-PTK2")
        alert = Alert(
            id="ALK2",
            patient_id="PTK2",
            category="lab",
            severity="high",
            title="Sodio bajo",
            detail="",
            source="risk_engine",
        )
        db_session.add_all([patient, alert])
        await db_session.flush()
        task, _ = await svc.create_task(
            db_session,
            source_type="alert",
            source_id=alert.id,
            category="alert",
            severity="high",
            title=alert.title,
            dedupe_key=f"alert:{alert.id}",
            patient_id=patient.id,
        )
        await db_session.commit()
        headers = await _clinician(client)

        res = await client.post(f"/api/tasks/{task.id}/complete", headers=headers)

        assert res.status_code == 200
        await db_session.refresh(alert)
        assert alert.status == "resolved"
        # Completing the task IS the review — without stamping it, the
        # dashboard's response-time metric would have no numerator.
        assert alert.reviewed_at is not None

    async def test_resolving_the_alert_closes_its_task(self, client, db_session):
        patient = Patient(id="PTK3", name="Cami", age=44, sex="F", medical_record_number="PT-PTK3")
        alert = Alert(
            id="ALK3",
            patient_id="PTK3",
            category="lab",
            severity="high",
            title="Creatinina alta",
            detail="",
            source="risk_engine",
        )
        db_session.add_all([patient, alert])
        await db_session.flush()
        task, _ = await svc.create_task(
            db_session,
            source_type="alert",
            source_id=alert.id,
            category="alert",
            severity="high",
            title=alert.title,
            dedupe_key=f"alert:{alert.id}",
            patient_id=patient.id,
        )
        await db_session.commit()
        headers = await _clinician(client)

        await client.post(f"/api/alerts/{alert.id}/review", headers=headers)
        await client.post(f"/api/alerts/{alert.id}/resolve", headers=headers)

        await db_session.refresh(task)
        assert task.status == "done"
        assert task.closed_by is not None

    async def test_an_approval_task_cannot_be_completed_from_the_inbox(self, client, db_session):
        """Closing the row is not consent to send the message it holds."""
        patient = Patient(id="PTK4", name="Dani", age=29, sex="M", medical_record_number="PT-PTK4")
        action = PendingAction(
            id="PA-K4",
            patient_id="PTK4",
            action_type="followup_check",
            draft_text="¿Cómo te sentís?",
        )
        db_session.add_all([patient, action])
        await db_session.flush()
        task, _ = await svc.create_task(
            db_session,
            source_type="approval",
            source_id=action.id,
            category="approval",
            severity="medium",
            title="Aprobar mensaje",
            dedupe_key=f"approval:{action.id}",
            patient_id=patient.id,
        )
        await db_session.commit()
        headers = await _clinician(client)

        listed = (await client.get("/api/tasks", headers=headers)).json()["items"][0]
        assert listed["completable"] is False
        assert "consent" in listed["completable_refusal"]

        res = await client.post(f"/api/tasks/{task.id}/complete", headers=headers)
        assert res.status_code == 409

        await db_session.refresh(action)
        assert action.status == "pending"


class TestCounters:
    async def test_counts_group_the_inbox_without_returning_any_content(self, client, seeded):
        headers = await _clinician(client)
        await client.post(f"/api/tasks/{seeded[0].id}/claim", headers=headers)

        counts = (await client.get("/api/tasks/count", headers=headers)).json()

        assert counts["open"] == 3
        assert counts["in_progress"] == 1
        assert counts["mine"] == 1
        assert counts["unassigned"] == 2

    async def test_badges_answer_every_counter_in_one_request(self, client, seeded, db_session):
        db_session.add(
            Alert(
                id="ALB1",
                patient_id="PTK1",
                category="lab",
                severity="low",
                title="x",
                detail="",
                source="risk_engine",
            )
        )
        await db_session.commit()
        headers = await _clinician(client)

        body = (await client.get("/api/badges", headers=headers)).json()

        assert body["tasks_open"] == 3
        assert body["alerts_active"] == 1
        assert body["notifications_unread"] == 0
        # Counters only — nothing here names a patient or a finding.
        assert all(isinstance(v, int) for v in body.values())
