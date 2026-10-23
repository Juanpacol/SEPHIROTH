"""The dashboard names the vital signs that put a patient out of range, with the
range and the reading before, so the clinician sees why without opening the chart."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Encounter, Patient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email) -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Vitals", "password": "password123"}
    )
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    me = await client.get("/api/auth/me", headers=headers)
    return headers, me.json()["id"]


def _patient(pid, name):
    return Patient(
        id=pid, name=name, age=60, sex="F", medical_record_number=f"PT-{pid}", lab_results={}, medications=[]
    )


def _visit(eid, pid, clinician_id, days_ago, vitals, status="signed"):
    started = datetime.utcnow() - timedelta(days=days_ago)
    signed = {"signed_by": clinician_id, "signed_at": started} if status == "signed" else {}
    return Encounter(
        **signed,
        id=eid,
        patient_id=pid,
        clinician_id=clinician_id,
        status=status,
        vitals=vitals,
        started_at=started,
    )


async def test_lists_out_of_range_vitals_worst_first_with_the_reading_before(client, db_session):
    headers, clinician_id = await _clinician(client, "vitals1@example.com")
    db_session.add_all(
        [
            _patient("V1", "Ana Ruiz"),
            _patient("V2", "Bruno Díaz"),
            _patient("V3", "Carla Mejía"),
            _patient("V4", "Diego Paz"),
        ]
    )
    db_session.add_all(
        [
            # Saturation well below normal, and it was 95 last visit.
            _visit("E1", "V1", clinician_id, 1, {"oxygen_saturation": 86, "heart_rate": 80}),
            _visit("E0", "V1", clinician_id, 20, {"oxygen_saturation": 95}),
            # Heart rate only slightly high.
            _visit("E2", "V2", clinician_id, 2, {"heart_rate": 104}),
            # All normal: never listed.
            _visit("E3", "V3", clinician_id, 1, {"heart_rate": 72, "oxygen_saturation": 98}),
            # Abnormal but a draft: not a recorded reading.
            _visit("E4", "V4", clinician_id, 1, {"oxygen_saturation": 70}, status="draft"),
        ]
    )
    await db_session.commit()

    res = await client.get("/api/dashboard/vitals", headers=headers)
    assert res.status_code == 200
    body = res.json()

    assert body["abnormal_patient_count"] == 2
    assert [p["patient_id"] for p in body["patients"]] == ["V1", "V2"]
    first = body["patients"][0]
    assert first["severity"] == "high"
    assert [f["key"] for f in first["findings"]] == ["oxygen_saturation"]
    spo2 = first["findings"][0]
    assert spo2["value"] == 86
    assert (spo2["low"], spo2["high"]) == (94, 100)
    assert spo2["previous"]["value"] == 95
    assert body["patients"][1]["findings"][0]["previous"] is None


async def test_empty_when_nobody_has_vitals(client):
    headers, _ = await _clinician(client, "vitals2@example.com")
    res = await client.get("/api/dashboard/vitals", headers=headers)
    assert res.json() == {"abnormal_patient_count": 0, "patients_with_vitals": 0, "patients": []}
