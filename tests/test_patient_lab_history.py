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


# --- where each result stands in its review (AB#24) -------------------------

PRIVATE_NOTE = "Sospecha de insuficiencia renal, no mencionar aún"


async def _record(client, headers, patient, test="potassium", value=6.2, unit="mEq/L", day=10):
    res = await client.post(
        "/api/results/labs",
        json={
            "patient_id": patient,
            "test_name": test,
            "value": value,
            "unit": unit,
            "taken_at": f"2026-10-{day:02d}T08:00:00+00:00",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _decide(client, headers, review_id, disposition="action_taken"):
    await client.post(
        f"/api/results/reviews/{review_id}/review",
        json={"disposition": disposition, "note": PRIVATE_NOTE},
        headers=headers,
    )


async def _tests(client, headers, patient="P1"):
    return {
        t["test_name"]: t
        for t in (await client.get(f"/api/patients/{patient}/labs", headers=headers)).json()["tests"]
    }


async def test_a_result_with_no_review_has_none_and_still_names_its_result(client, db_session):
    await _patients(db_session, "P1")
    db_session.add(_lab("P1", "sodium", 139))
    await db_session.commit()

    (test,) = (await _tests(client, await _clinician(client))).values()

    assert test["review"] is None
    assert isinstance(test["result_id"], int)


async def test_a_newly_recorded_result_is_received_and_nobody_has_decided_yet(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    await _record(client, headers, "P1")

    review = (await _tests(client, headers))["potassium"]["review"]

    assert review["status"] == "received" and review["id"]
    assert (
        review["disposition"],
        review["reviewed_by"],
        review["reviewed_at"],
        review["communicated_at"],
    ) == (
        None,
        None,
        None,
        None,
    )


async def test_a_reviewed_result_says_what_was_decided_by_whom_and_when(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    rid = await _record(client, headers, "P1")
    await _decide(client, headers, rid)

    review = (await _tests(client, headers))["potassium"]["review"]

    assert review["status"] == "reviewed" and review["disposition"] == "action_taken"
    assert review["reviewed_by"] == "Dr. L" and review["reviewed_at"]
    assert review["communicated_at"] is None


async def test_a_communicated_result_says_when_the_patient_was_told(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    rid = await _record(client, headers, "P1")
    await _decide(client, headers, rid, "needs_patient_contact")
    await client.post(
        f"/api/results/reviews/{rid}/communicate", json={"message": "Llámenos"}, headers=headers
    )

    review = (await _tests(client, headers))["potassium"]["review"]

    assert review["status"] == "communicated" and review["communicated_at"]


async def test_a_closed_result_is_closed(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    rid = await _record(client, headers, "P1")
    await _decide(client, headers, rid)
    await client.post(f"/api/results/reviews/{rid}/close", headers=headers)

    assert (await _tests(client, headers))["potassium"]["review"]["status"] == "closed"


async def test_the_state_is_the_one_of_the_latest_reading_not_an_older_one(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    old = await _record(client, headers, "P1", value=5.0, day=5)
    await _decide(client, headers, old)
    await _record(client, headers, "P1", value=6.2, day=12)

    test = (await _tests(client, headers))["potassium"]

    assert test["entries"][0]["value"] == 6.2
    assert test["review"]["status"] == "received", (
        "the older reading's review must not stand in for the new one"
    )


async def test_the_private_note_never_leaves(client, db_session):
    await _patients(db_session, "P1")
    headers = await _clinician(client)
    rid = await _record(client, headers, "P1")
    await _decide(client, headers, rid)

    res = await client.get("/api/patients/P1/labs", headers=headers)

    assert PRIVATE_NOTE not in res.text and '"note"' not in res.text


async def test_the_number_of_queries_does_not_grow_with_the_number_of_tests(client, db_session):
    from sqlalchemy import event

    await _patients(db_session, "P1")
    headers = await _clinician(client)
    counts = []
    for n in (2, 12):
        for i in range(n):
            rid = await _record(client, headers, "P1", test=f"test_{n}_{i}", value=1.0 + i)
            await _decide(client, headers, rid)
        statements = []

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        engine = db_session.bind.sync_engine
        event.listen(engine, "before_cursor_execute", count)
        try:
            await client.get("/api/patients/P1/labs", headers=headers)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        counts.append(len(statements))

    assert counts[0] == counts[1], counts


async def test_one_patients_reviews_do_not_appear_on_another(client, db_session):
    await _patients(db_session, "P1", "P2")
    headers = await _clinician(client)
    rid = await _record(client, headers, "P1", test="potassium")
    await _decide(client, headers, rid)
    db_session.add(_lab("P2", "potassium", 4.0))
    await db_session.commit()

    assert (await _tests(client, headers, "P2"))["potassium"]["review"] is None
