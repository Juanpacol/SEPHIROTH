"""SPEC-031 1.1.0: which clinical problems dominate across all patients.

The counts must be exact (every patient, the same population as /stats), not
derived from the action list, which is capped per category.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient

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
        "/api/auth/register", json={"email": email, "name": "Dr. Summary", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _patient(pid, name, labs=None, meds=None):
    return Patient(
        id=pid,
        name=name,
        age=60,
        sex="F",
        medical_record_number=f"PT-{pid}",
        lab_results=labs or {},
        medications=meds or [],
    )


async def _seed(db_session):
    db_session.add_all(
        [
            # High risk: hyperkalemia + hypertension.
            _patient("RS1", "Bruno Díaz", {"potassium": "6.8", "bp": "170/95"}),
            # High risk: hyperkalemia + two different interactions (one bucket).
            _patient(
                "RS2",
                "Ana Ruiz",
                {"potassium": "6.2"},
                ["warfarin", "aspirin", "lisinopril", "spironolactone"],
            ),
            # Medium risk: hypertension only.
            _patient("RS3", "Aaron Soto", {"bp": "165/90"}),
            # High risk: very high LDL only.
            _patient("RS4", "Carla Mejía", {"ldl": "200"}),
            # No flags at all.
            _patient("RS5", "Diego Paz", {"potassium": "4.2"}),
        ]
    )
    await db_session.commit()


async def _summary(client, email):
    headers = await _clinician(client, email)
    res = await client.get("/api/dashboard/rule-summary", headers=headers)
    assert res.status_code == 200
    return res.json(), headers


async def test_counts_distinct_patients_per_rule_over_the_stats_population(client, db_session):
    """AC-031-10: counts are distinct patients per rule_code, over every patient
    /stats assesses; two interaction flags on one patient count once."""
    await _seed(db_session)
    body, headers = await _summary(client, "rs-counts@example.org")

    counts = {rule["rule_code"]: rule["count"] for rule in body["rules"]}
    assert counts == {
        "hyperkalemia": 2,
        "hypertensive_range": 2,
        "drug_interaction": 1,
        "very_high_ldl_cholesterol": 1,
    }
    stats = (await client.get("/api/dashboard/stats", headers=headers)).json()
    assert (
        body["total_patients"]
        == stats["critical_count"] + stats["moderate_count"] + stats["stable_count"]
        == 5
    )


async def test_rules_are_ordered_by_count_then_severity_then_code(client, db_session):
    """AC-031-11: count desc, then high before medium, then rule_code."""
    await _seed(db_session)
    body, _ = await _summary(client, "rs-order@example.org")

    assert [rule["rule_code"] for rule in body["rules"]] == [
        "hyperkalemia",  # 2, high
        "hypertensive_range",  # 2, medium
        "drug_interaction",  # 1, high
        "very_high_ldl_cholesterol",  # 1, high
    ]


async def test_each_rule_lists_its_patients_by_risk_then_name(client, db_session):
    """AC-031-12: count == len(patients); patients carry id/name/risk_level,
    ordered by risk (high first) then name."""
    await _seed(db_session)
    body, _ = await _summary(client, "rs-patients@example.org")
    rules = {rule["rule_code"]: rule for rule in body["rules"]}

    for rule in body["rules"]:
        assert rule["count"] == len(rule["patients"])
    assert [p["name"] for p in rules["hyperkalemia"]["patients"]] == ["Ana Ruiz", "Bruno Díaz"]
    assert rules["hypertensive_range"]["patients"] == [
        {"id": "RS1", "name": "Bruno Díaz", "risk_level": "high"},
        {"id": "RS3", "name": "Aaron Soto", "risk_level": "medium"},
    ]


async def test_all_interactions_share_one_bucket(client, db_session):
    """AC-031-13: every drug pair aggregates into drug_interaction, with the
    worst severity among them."""
    await _seed(db_session)
    body, _ = await _summary(client, "rs-drugs@example.org")

    buckets = [rule for rule in body["rules"] if rule["rule_code"] == "drug_interaction"]
    assert len(buckets) == 1
    assert buckets[0]["severity"] == "high"
    assert buckets[0]["label"] == "Interaction"
    assert [p["id"] for p in buckets[0]["patients"]] == ["RS2"]


async def test_no_flags_yields_no_rules_but_a_correct_population(client, db_session):
    """AC-031-14: with no firing flags, rules == [] and total_patients still
    counts the population."""
    db_session.add_all([_patient("RS6", "Elena Gil", {"potassium": "4.4"}), _patient("RS7", "Fabio León")])
    await db_session.commit()
    body, _ = await _summary(client, "rs-empty@example.org")

    assert body == {"total_patients": 2, "rules": []}


async def test_rule_summary_is_clinician_only(client):
    """AC-031-14: an unauthenticated request is rejected."""
    res = await client.get("/api/dashboard/rule-summary")
    assert res.status_code in (401, 403)
