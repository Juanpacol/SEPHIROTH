"""API tests for `/api/results/{shareable,shares}` — sharing a
`TimelineEvent` with the patient it belongs to, built against the real
`api.main.app` wiring."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, TimelineEvent, User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician_headers(client, email="results-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Results", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def patient_with_events(db_session):
    p = Patient(id="PRESULT1", name="Result Patient", age=45, sex="F", medical_record_number="PT-PRESULT1")
    db_session.add(p)
    lab = TimelineEvent(patient_id=p.id, date=date(2026, 1, 1), type="lab", title="A1C 6.1%")
    diagnosis = TimelineEvent(patient_id=p.id, date=date(2026, 1, 2), type="diagnosis", title="Hypertension")
    db_session.add_all([lab, diagnosis])
    await db_session.commit()
    return p, lab, diagnosis


@pytest.fixture
async def patient_token(db_session, patient_with_events):
    p, _, _ = patient_with_events
    user = User(
        id="user-presult1",
        email="presult1@example.org",
        name="Result Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=p.id,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def test_shareable_events_lists_only_lab_and_imaging(client, patient_with_events):
    p, lab, diagnosis = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        res = await client.get(f"/api/results/shareable/{p.id}", headers=headers)
        assert res.status_code == 200
        types = {e["type"] for e in res.json()}
        assert types == {"lab"}
        assert res.json()[0]["already_shared"] is False


async def test_share_lab_result_and_patient_can_read_it(client, patient_with_events, patient_token):
    p, lab, _ = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id, "message": "Your A1C looks good."},
            headers=headers,
        )
        assert share_res.status_code == 201
        share_id = share_res.json()["id"]
        assert share_res.json()["event"]["title"] == "A1C 6.1%"

        patient_view = await client.get(
            "/api/results/shares", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert patient_view.status_code == 200
        assert len(patient_view.json()) == 1
        assert patient_view.json()[0]["id"] == share_id


async def test_sharing_a_diagnosis_event_rejected(client, patient_with_events):
    p, _, diagnosis = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": diagnosis.id},
            headers=headers,
        )
        assert res.status_code == 422


async def test_event_patient_mismatch_rejected(client, patient_with_events, db_session):
    p, lab, _ = patient_with_events
    other = Patient(id="PRESULT2", name="Other", age=30, sex="M", medical_record_number="PT-PRESULT2")
    db_session.add(other)
    await db_session.commit()
    async with client:
        headers = await _clinician_headers(client)
        res = await client.post(
            "/api/results/shares",
            json={"patient_id": other.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        assert res.status_code == 422


async def test_duplicate_share_conflicts(client, patient_with_events):
    p, lab, _ = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        assert res.status_code == 409


async def test_viewed_at_stamped_once_by_patient(client, patient_with_events, patient_token):
    p, lab, _ = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]
        assert share_res.json()["viewed_at"] is None

        first_view = await client.get(
            f"/api/results/shares/{share_id}", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert first_view.json()["viewed_at"] is not None
        stamped_at = first_view.json()["viewed_at"]

        second_view = await client.get(
            f"/api/results/shares/{share_id}", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert second_view.json()["viewed_at"] == stamped_at


async def test_patient_cannot_read_another_patients_share(client, patient_with_events, db_session):
    p, lab, _ = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        other = Patient(id="PRESULT3", name="Other B", age=50, sex="F", medical_record_number="PT-PRESULT3")
        db_session.add(other)
        other_user = User(
            id="user-other-b",
            email="otherb@example.org",
            name="Other B",
            hashed_password=await hash_password("password123"),
            role="patient",
            patient_id=other.id,
        )
        db_session.add(other_user)
        await db_session.commit()
        other_token = create_access_token(other_user.id)

        res = await client.get(
            f"/api/results/shares/{share_id}", headers={"Authorization": f"Bearer {other_token}"}
        )
        assert res.status_code == 404


async def test_revoked_share_hidden_from_patient(client, patient_with_events, patient_token):
    p, lab, _ = patient_with_events
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": lab.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        revoke_res = await client.delete(f"/api/results/shares/{share_id}", headers=headers)
        assert revoke_res.status_code == 204

        patient_view = await client.get(
            "/api/results/shares", headers={"Authorization": f"Bearer {patient_token}"}
        )
        assert patient_view.json() == []
