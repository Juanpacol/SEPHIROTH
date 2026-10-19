"""`GET /api/patients/{id}/labs`: the history behind the lab card (AB#20)."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.main import app
from core.db import get_session
from data.schemas import LabResult, Patient, PhiAccessLog

pytestmark = pytest.mark.asyncio

BASE = datetime(2026, 10, 1, 9, 0)


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="labs@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. L", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _lab(patient, test, value, days=0, *, unit="", low=None, high=None, abnormal=False, critical=False):
    return LabResult(
        patient_id=patient,
        test_name=test,
        value=value,
        unit=unit,
        reference_low=low,
        reference_high=high,
        is_abnormal=abnormal,
        is_critical=critical,
        taken_at=BASE + timedelta(days=days),
    )


async def _patients(db_session, *ids):
    for pid in ids:
        db_session.add(
            Patient(id=pid, name=f"Patient {pid}", age=50, sex="F", medical_record_number=f"PT-{pid}")
        )
    await db_session.commit()


async def test_each_reading_carries_the_range_it_was_judged_against(client, db_session):
    await _patients(db_session, "P1")
    db_session.add_all(
        [
            _lab("P1", "potassium", 6.4, 2, unit="mmol/L", low=3.5, high=5.1, abnormal=True, critical=True),
            _lab("P1", "potassium", 5.0, 1, unit="mmol/L", low=3.5, high=5.1),
        ]
    )
    await db_session.commit()

    res = await client.get("/api/patients/P1/labs", headers=await _clinician(client))

    (test,) = res.json()["tests"]
    assert test["test_name"] == "potassium" and test["unit"] == "mmol/L"
    assert [e["value"] for e in test["entries"]] == [6.4, 5.0], "newest first"
    assert test["entries"][0] == {
        "value": 6.4,
        "taken_at": "2026-10-03T09:00:00",
        "is_abnormal": True,
        "is_critical": True,
        "reference_low": 3.5,
        "reference_high": 5.1,
    }


async def test_a_reading_with_no_known_range_says_null_not_zero(client, db_session):
    await _patients(db_session, "P1")
    db_session.add(_lab("P1", "ldl", 162, unit="mg/dL", high=100, abnormal=True))
    db_session.add(_lab("P1", "mystery", 1.0))
    await db_session.commit()

    tests = {
        t["test_name"]: t
        for t in (await client.get("/api/patients/P1/labs", headers=await _clinician(client))).json()["tests"]
    }

    assert tests["ldl"]["entries"][0]["reference_low"] is None
    assert tests["ldl"]["entries"][0]["reference_high"] == 100
    assert (
        tests["mystery"]["entries"][0]["reference_low"] is None
        and tests["mystery"]["entries"][0]["reference_high"] is None
    )


async def test_the_range_can_differ_between_readings_of_the_same_test(client, db_session):
    await _patients(db_session, "P1")
    db_session.add_all(
        [
            _lab("P1", "potassium", 5.2, 2, high=5.1, abnormal=True),
            _lab("P1", "potassium", 5.2, 1, high=5.5),
        ]
    )
    await db_session.commit()

    (test,) = (await client.get("/api/patients/P1/labs", headers=await _clinician(client))).json()["tests"]

    assert [e["reference_high"] for e in test["entries"]] == [5.1, 5.5]


async def test_worst_first_and_only_this_patients_results(client, db_session):
    await _patients(db_session, "P1", "P2")
    db_session.add_all(
        [
            _lab("P1", "sodium", 139),
            _lab("P1", "ldl", 162, abnormal=True),
            _lab("P1", "potassium", 6.4, critical=True, abnormal=True),
            _lab("P2", "hba1c", 9.0, abnormal=True),
        ]
    )
    await db_session.commit()

    tests = (await client.get("/api/patients/P1/labs", headers=await _clinician(client))).json()["tests"]

    assert [t["test_name"] for t in tests] == ["potassium", "ldl", "sodium"]


async def test_history_per_test_is_capped(client, db_session):
    await _patients(db_session, "P1")
    db_session.add_all([_lab("P1", "sodium", 130 + i, i) for i in range(25)])
    await db_session.commit()

    (test,) = (await client.get("/api/patients/P1/labs", headers=await _clinician(client))).json()["tests"]

    assert len(test["entries"]) == 20 and test["entries"][0]["value"] == 154


async def test_a_patient_with_no_labs_gets_an_empty_list(client, db_session):
    await _patients(db_session, "P1")

    res = await client.get("/api/patients/P1/labs", headers=await _clinician(client))

    assert res.status_code == 200 and res.json() == {"tests": []}


async def test_unknown_patient_is_404_and_no_token_is_401(client, db_session):
    headers = await _clinician(client)

    assert (await client.get("/api/patients/nope/labs", headers=headers)).status_code == 404
    assert (await client.get("/api/patients/nope/labs")).status_code == 401


async def test_reading_the_history_is_audited(client, db_session):
    await _patients(db_session, "P1")

    await client.get("/api/patients/P1/labs", headers=await _clinician(client))

    rows = (await db_session.execute(select(PhiAccessLog))).scalars().all()
    assert [(r.patient_id, r.method) for r in rows if "labs" in r.route] == [("P1", "GET")]
