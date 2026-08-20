"""API tests for `/api/results/shares/{id}/attachments` and
`/api/results/attachments/{id}/download` — upload caps, MIME allowlist,
and download authorization scoping."""

import hashlib
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


async def _clinician_headers(client, email="attach-clin@example.org") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Attach", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def share(db_session):
    p = Patient(id="PATT1", name="Attach Patient", age=38, sex="F", medical_record_number="PT-PATT1")
    db_session.add(p)
    event = TimelineEvent(patient_id=p.id, date=date(2026, 1, 1), type="lab", title="CBC")
    db_session.add(event)
    await db_session.commit()
    return p, event


@pytest.fixture
async def patient_token(db_session, share):
    p, _ = share
    user = User(
        id="user-patt1",
        email="patt1@example.org",
        name="Attach Patient",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=p.id,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def test_upload_and_download_happy_path(client, share):
    p, event = share
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        content = b"%PDF-1.4 fake pdf bytes"
        upload = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("report.pdf", content, "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 201
        att_id = upload.json()["id"]
        assert upload.json()["filename"] == "report.pdf"
        assert upload.json()["size_bytes"] == len(content)

        download = await client.get(f"/api/results/attachments/{att_id}/download", headers=headers)
        assert download.status_code == 200
        assert download.content == content
        assert "attachment" in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"


async def test_oversized_attachment_rejected(client, share):
    p, event = share
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        oversized = b"x" * (10 * 1024 * 1024 + 1)
        upload = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("big.pdf", oversized, "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 413


async def test_disallowed_content_type_rejected(client, share):
    p, event = share
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        upload = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("script.js", b"alert(1)", "application/javascript")},
            headers=headers,
        )
        assert upload.status_code == 415


async def test_fourth_attachment_rejected(client, share):
    p, event = share
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]

        for i in range(3):
            res = await client.post(
                f"/api/results/shares/{share_id}/attachments",
                files={"file": (f"f{i}.pdf", b"data", "application/pdf")},
                headers=headers,
            )
            assert res.status_code == 201

        fourth = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("f4.pdf", b"data", "application/pdf")},
            headers=headers,
        )
        assert fourth.status_code == 422


async def test_download_authz_owning_patient_ok_other_patient_404(client, share, patient_token, db_session):
    p, event = share
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]
        upload = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("report.pdf", b"content", "application/pdf")},
            headers=headers,
        )
        att_id = upload.json()["id"]

        owner_download = await client.get(
            f"/api/results/attachments/{att_id}/download",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert owner_download.status_code == 200

        other_patient = Patient(id="PATT2", name="Other", age=29, sex="M", medical_record_number="PT-PATT2")
        db_session.add(other_patient)
        other_user = User(
            id="user-patt2",
            email="patt2@example.org",
            name="Other",
            hashed_password=await hash_password("password123"),
            role="patient",
            patient_id=other_patient.id,
        )
        db_session.add(other_user)
        await db_session.commit()
        other_token = create_access_token(other_user.id)

        other_download = await client.get(
            f"/api/results/attachments/{att_id}/download",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert other_download.status_code == 404


async def test_sha256_recorded_correctly(client, share, db_session):
    p, event = share
    content = b"deterministic content"
    async with client:
        headers = await _clinician_headers(client)
        share_res = await client.post(
            "/api/results/shares",
            json={"patient_id": p.id, "timeline_event_id": event.id},
            headers=headers,
        )
        share_id = share_res.json()["id"]
        upload = await client.post(
            f"/api/results/shares/{share_id}/attachments",
            files={"file": ("f.pdf", content, "application/pdf")},
            headers=headers,
        )
        att_id = upload.json()["id"]

    from data.schemas import ResultAttachment

    row = await db_session.get(ResultAttachment, att_id)
    assert row.sha256 == hashlib.sha256(content).hexdigest()
