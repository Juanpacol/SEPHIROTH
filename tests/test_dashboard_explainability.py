"""SPEC-031: dashboard action items explain why they fired, how the triggering
test has moved, and whether an alert is new or recurring."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Alert, LabResult, Patient, PendingAction

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email) -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Why", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _items(client, email):
    headers = await _clinician(client, email)
    body = (await client.get("/api/dashboard/action-items", headers=headers)).json()
    return [item for group in body["groups"] for item in group["items"]]


def _alert(patient_id, title, *, status="active", created_at=None, resolved_at=None, source="risk_engine"):
    return Alert(
        id=str(uuid4()),
        patient_id=patient_id,
        category="lab",
        severity="high",
        status=status,
        title=title,
        detail="",
        source=source,
        created_at=created_at or _now(),
        resolved_at=resolved_at,
    )


async def test_alert_item_explains_the_flag_that_still_fires(client, db_session):
    """AC-031-05: a risk_engine alert carries the factors of the patient's
    currently firing flag with the same label; a flag that stopped firing
    leaves the alert listed with null factors."""
    db_session.add(
        Patient(
            id="PX1",
            name="Nida Deckow",
            age=70,
            sex="F",
            medical_record_number="PT-PX1",
            lab_results={"potassium": "6.8 mEq/L"},
        )
    )
    db_session.add_all([_alert("PX1", "Hyperkalemia"), _alert("PX1", "Supratherapeutic INR")])
    await db_session.commit()

    alerts = {
        i["title"]: i for i in await _items(client, "why-alert@example.org") if i["category"] == "alert"
    }

    firing = alerts["Hyperkalemia"]
    assert firing["rule_code"] == "hyperkalemia"
    assert firing["factors"] == [
        {"test": "potassium", "value": 6.8, "comparator": ">", "threshold": 5.5, "unit": "mEq/L"}
    ]
    stale = alerts["Supratherapeutic INR"]
    assert stale["rule_code"] is None
    assert stale["factors"] is None


async def test_lab_item_carries_factors_and_a_plausible_trend(client, db_session):
    """AC-031-06: a critical lab item explains its value and carries at most the
    last 5 plausible readings of that test, oldest first; an implausible
    reading never enters the trend."""
    db_session.add(
        Patient(id="PX2", name="Gordon Bartoletti", age=66, sex="M", medical_record_number="PT-PX2")
    )
    base = datetime(2026, 9, 1)
    for day, value in enumerate([4.1, 4.4, 4.9, 5.2, 5.9, 6.8]):
        db_session.add(
            LabResult(
                patient_id="PX2",
                test_name="potassium",
                value=value,
                unit="mEq/L",
                is_abnormal=value > 5.5,
                is_critical=value > 5.5,
                taken_at=base + timedelta(days=day),
            )
        )
    for day, (sys, dia) in enumerate([(150, 95), (1314, 653), (185, 112)]):
        for name, value in (("bp_systolic", sys), ("bp_diastolic", dia)):
            db_session.add(
                LabResult(
                    patient_id="PX2",
                    test_name=name,
                    value=value,
                    unit="mmHg",
                    is_abnormal=True,
                    is_critical=day == 2,
                    taken_at=base + timedelta(days=day),
                )
            )
    await db_session.commit()

    labs = {i["test_name"]: i for i in await _items(client, "why-lab@example.org") if i["category"] == "lab"}

    potassium = labs["potassium"]
    assert potassium["rule_code"] == "hyperkalemia"
    assert potassium["factors"][0]["value"] == 6.8
    assert [point["value"] for point in potassium["trend"]] == [4.4, 4.9, 5.2, 5.9, 6.8]
    assert potassium["trend"][0]["taken_at"] < potassium["trend"][-1]["taken_at"]

    systolic = labs["bp_systolic"]
    assert systolic["rule_code"] == "hypertensive_range"
    assert [f["value"] for f in systolic["factors"]] == [185.0, 112.0]
    assert [point["value"] for point in systolic["trend"]] == [150.0, 185.0]


async def test_alert_item_says_how_long_it_has_been_active_and_how_often_it_recurred(client, db_session):
    """AC-031-07: active_since is the alert's created_at; prior_count counts only
    resolved alerts of the same patient and title resolved in the last 30 days."""
    db_session.add(
        Patient(
            id="PX3",
            name="Arnulfo Murphy",
            age=59,
            sex="M",
            medical_record_number="PT-PX3",
            lab_results={"potassium": "6.1"},
        )
    )
    now = _now()
    active_since = now - timedelta(days=3)
    db_session.add_all(
        [
            _alert("PX3", "Hyperkalemia", created_at=active_since),
            _alert("PX3", "Hyperkalemia", status="resolved", resolved_at=now - timedelta(days=10)),
            _alert("PX3", "Hyperkalemia", status="resolved", resolved_at=now - timedelta(days=20)),
            _alert("PX3", "Hyperkalemia", status="resolved", resolved_at=now - timedelta(days=45)),
            _alert("PX3", "Obesity", status="resolved", resolved_at=now - timedelta(days=5)),
        ]
    )
    await db_session.commit()

    (item,) = [i for i in await _items(client, "why-recur@example.org") if i["category"] == "alert"]

    assert item["recurrence"] == {"active_since": active_since.isoformat(), "prior_count": 2}


async def test_signals_with_nothing_to_explain_carry_nulls(client, db_session):
    """AC-031-08: approval items carry null enrichment; an interaction item is
    coded drug_interaction with no trend."""
    db_session.add(
        Patient(
            id="PX4",
            name="Juan Pérez",
            age=68,
            sex="M",
            medical_record_number="PT-PX4",
            medications=["warfarin", "aspirin"],
            status="active",
        )
    )
    db_session.add(
        PendingAction(
            id=str(uuid4()),
            patient_id="PX4",
            action_type="followup_day7",
            status="pending",
            draft_text="",
            draft_source="template",
        )
    )
    await db_session.commit()

    items = {i["category"]: i for i in await _items(client, "why-null@example.org")}

    approval = items["approval"]
    assert (approval["rule_code"], approval["factors"], approval["trend"], approval["recurrence"]) == (
        None,
        None,
        None,
        None,
    )
    interaction = items["interaction"]
    assert interaction["rule_code"] == "drug_interaction"
    assert interaction["factors"] == []
    assert interaction["trend"] is None
    assert interaction["recurrence"] is None


async def test_stats_and_bootstrap_keep_their_shapes(client):
    """AC-031-09: enrichment is confined to action items."""
    headers = await _clinician(client, "why-shape@example.org")
    stats = (await client.get("/api/dashboard/stats", headers=headers)).json()
    assert set(stats) == {
        "critical_patients",
        "critical_count",
        "moderate_count",
        "stable_count",
        "at_risk_count",
        "max_priority_score",
        "avg_priority_score",
    }
    bootstrap = (await client.get("/api/dashboard/bootstrap", headers=headers)).json()
    assert set(bootstrap) == {"stats", "agenda", "action_items"}
    assert set(bootstrap["action_items"]) == {"groups", "total_count"}
