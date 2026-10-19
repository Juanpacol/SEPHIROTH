"""What a patient sees of their labs: only what a clinician communicated (AB#23)."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import LabResult, Patient, PhiAccessLog, ResultShare, TimelineEvent, User

pytestmark = pytest.mark.asyncio

CLINICIAN = {"email": "labs-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}
PRIVATE_NOTE = "Sospecha de hipoparatiroidismo, confirmar antes de hablar de ello"


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


@pytest.fixture
async def doctor(client):
    token = (await client.post("/api/auth/register", json=CLINICIAN)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _patient_with_portal(db_session, pid, email, *, snapshot=None):
    db_session.add(
        Patient(
            id=pid,
            name=f"Paciente {pid}",
            age=50,
            sex="F",
            medical_record_number=f"MRN-{pid}",
            lab_results=snapshot or {},
        )
    )
    await db_session.commit()
    user = User(
        id=f"u-{pid}",
        email=email,
        name=f"Paciente {pid}",
        hashed_password=await hash_password("password123"),
        role="patient",
        patient_id=pid,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def ana(db_session):
    return await _patient_with_portal(
        db_session, "PAN", "ana-labs@example.org", snapshot={"secret_snapshot": "99 mg/dL"}
    )


async def _lab(client, doctor, patient_id, test="potassium", value=6.2, unit="mEq/L", days=0, **extra):
    taken = (datetime(2026, 10, 10, 8, 0) + timedelta(days=days)).isoformat() + "+00:00"
    res = await client.post(
        "/api/results/labs",
        json={
            "patient_id": patient_id,
            "test_name": test,
            "value": value,
            "unit": unit,
            "taken_at": taken,
            **extra,
        },
        headers=doctor,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _review(client, doctor, review_id, disposition="needs_patient_contact", note=PRIVATE_NOTE):
    await client.post(
        f"/api/results/reviews/{review_id}/review",
        json={"disposition": disposition, "note": note},
        headers=doctor,
    )


async def _tell(client, doctor, review_id, message="Por favor llame a la clínica."):
    res = await client.post(
        f"/api/results/reviews/{review_id}/communicate", json={"message": message}, headers=doctor
    )
    assert res.status_code == 200, res.text
    return res.json()["share_id"]


async def _communicated(client, doctor, patient_id, **lab):
    rid = await _lab(client, doctor, patient_id, **lab)
    await _review(client, doctor, rid)
    return await _tell(client, doctor, rid)


async def _labs(client, headers):
    res = await client.get("/api/portal/labs", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["labs"]


# --- what is shown ---------------------------------------------------------


async def test_a_communicated_lab_is_shown_with_what_a_patient_needs(client, doctor, ana):
    share_id = await _communicated(client, doctor, "PAN", reference_low=3.5, reference_high=5.1)

    (lab,) = await _labs(client, ana)

    assert lab == {
        "share_id": share_id,
        "test_name": "potassium",
        "value": 6.2,
        "unit": "mEq/L",
        "taken_at": "2026-10-10T08:00:00",
        "reference_low": 3.5,
        "reference_high": 5.1,
        "standing": "needs_attention",
        "direction": "above",
        "message": "Por favor llame a la clínica.",
        "shared_at": lab["shared_at"],
        "viewed_at": None,
    }


async def test_a_result_that_was_reviewed_but_not_communicated_is_not_shown(client, doctor, ana):
    reviewed = await _lab(client, doctor, "PAN", test="sodium", value=128)
    await _review(client, doctor, reviewed)
    await _lab(client, doctor, "PAN", test="calcium", value=7.0, days=1)  # received, never reviewed

    assert await _labs(client, ana) == []


async def test_the_snapshot_values_are_no_longer_exposed(client, doctor, ana):
    res = await client.get("/api/portal/labs", headers=ana)

    assert res.json()["labs"] == []
    assert "secret_snapshot" not in res.text and "lab_results" not in res.json()


async def test_nothing_private_about_the_review_ever_reaches_the_patient(client, doctor, ana):
    share_id = await _communicated(client, doctor, "PAN")

    responses = [
        await client.get("/api/portal/labs", headers=ana),
        await client.get("/api/results/shares", headers=ana),
        await client.get(f"/api/results/shares/{share_id}", headers=ana),
    ]

    for res in responses:
        assert PRIVATE_NOTE not in res.text
        for word in (
            "disposition",
            "needs_patient_contact",
            "classification_reason",
            "reviewed_by",
            "severity",
            "note",
        ):
            assert word not in res.text, word


async def test_newest_first_and_revoked_shares_are_hidden(client, doctor, ana, db_session):
    old = await _communicated(client, doctor, "PAN", test="sodium", value=139, days=0)
    new = await _communicated(client, doctor, "PAN", test="potassium", value=6.2, days=1)
    gone = await _communicated(client, doctor, "PAN", test="calcium", value=7.0, days=2)
    share = await db_session.get(ResultShare, gone)
    share.status = "revoked"
    old_share = await db_session.get(ResultShare, old)
    old_share.shared_at = datetime(2026, 10, 1)
    await db_session.commit()

    assert [lab["share_id"] for lab in await _labs(client, ana)] == [new, old]


async def test_a_share_whose_result_was_deleted_is_skipped_not_half_shown(client, doctor, ana, db_session):
    share_id = await _communicated(client, doctor, "PAN")
    await _communicated(client, doctor, "PAN", test="sodium", value=139, days=1)
    share = await db_session.get(ResultShare, share_id)
    row = await db_session.get(LabResult, int(share.result_id))
    await db_session.delete(row)
    await db_session.commit()

    assert [lab["test_name"] for lab in await _labs(client, ana)] == ["sodium"]


async def test_an_imaging_share_is_not_a_lab(client, doctor, ana):
    study = (
        await client.post(
            "/api/results/imaging",
            json={"patient_id": "PAN", "modality": "cr", "body_part": "chest", "severity": "review"},
            headers=doctor,
        )
    ).json()["id"]
    await _review(client, doctor, study)
    await _tell(client, doctor, study)

    assert await _labs(client, ana) == []


async def test_a_share_is_a_lab_only_by_its_type_not_by_the_shape_of_its_id(client, doctor, ana, db_session):
    rid = await _lab(client, doctor, "PAN", test="sodium", value=139, unit="mmol/L")
    lab_id = (await client.get(f"/api/results/reviews/{rid}", headers=doctor)).json()["result_id"]
    event = TimelineEvent(
        patient_id="PAN", date=datetime(2026, 10, 10).date(), type="imaging", title="Chest X-ray"
    )
    db_session.add(event)
    await db_session.flush()
    doc = (await db_session.execute(select(User).where(User.email == CLINICIAN["email"]))).scalars().one()
    db_session.add(
        ResultShare(
            id="share-imaging-numeric",
            patient_id="PAN",
            timeline_event_id=event.id,
            shared_by_user_id=doc.id,
            result_type="imaging",
            result_id=lab_id,
        )
    )
    await db_session.commit()

    assert await _labs(client, ana) == []


# --- where the value sits against its range ---------------------------------


@pytest.mark.parametrize(
    "lab,standing,direction",
    [
        ({"test": "sodium", "value": 139, "unit": "mmol/L"}, "inside", None),
        ({"test": "hemoglobin", "value": 10.1, "unit": "g/dL"}, "outside", "below"),
        ({"test": "hba1c", "value": 6.8, "unit": "%"}, "outside", "above"),
        ({"test": "potassium", "value": 6.4, "unit": "mEq/L"}, "needs_attention", None),
    ],
)
async def test_standing_and_direction_follow_the_reviewed_classification(
    client, doctor, ana, lab, standing, direction
):
    await _communicated(client, doctor, "PAN", **lab)

    (shown,) = await _labs(client, ana)

    assert (shown["standing"], shown["direction"]) == (standing, direction)


async def test_a_result_with_no_review_behind_it_has_an_unknown_standing(client, doctor, ana, db_session):
    rid = await _lab(client, doctor, "PAN", test="sodium", value=139, unit="mmol/L")
    share_id = await _tell_without_review(client, doctor, db_session, rid)

    (shown,) = await _labs(client, ana)

    assert shown["share_id"] == share_id and shown["standing"] == "unknown" and shown["direction"] is None


async def _tell_without_review(client, doctor, db_session, review_id):
    review = (await client.get(f"/api/results/reviews/{review_id}", headers=doctor)).json()
    event = TimelineEvent(patient_id="PAN", date=datetime(2026, 10, 10).date(), type="lab", title="Sodium")
    db_session.add(event)
    await db_session.flush()
    doc = (await db_session.execute(select(User).where(User.email == CLINICIAN["email"]))).scalars().one()
    share = ResultShare(
        id="share-no-review",
        patient_id="PAN",
        timeline_event_id=event.id,
        shared_by_user_id=doc.id,
        message="",
        result_type="lab",
        result_id=review["result_id"],
    )
    db_session.add(share)
    await db_session.commit()
    return share.id


# --- who sees what ----------------------------------------------------------


async def test_a_patient_never_sees_another_patients_results(client, doctor, ana, db_session):
    bea = await _patient_with_portal(db_session, "PBE", "bea-labs@example.org")
    ana_share = await _communicated(client, doctor, "PAN", test="sodium", value=139)
    bea_share = await _communicated(client, doctor, "PBE", test="potassium", value=6.2)

    assert [lab["share_id"] for lab in await _labs(client, ana)] == [ana_share]
    assert [lab["share_id"] for lab in await _labs(client, bea)] == [bea_share]
    assert (await client.get(f"/api/results/shares/{bea_share}", headers=ana)).status_code == 404


async def test_the_patient_comes_from_the_token_not_from_a_parameter(client, doctor, ana, db_session):
    bea = await _patient_with_portal(db_session, "PBE", "bea2-labs@example.org")
    await _communicated(client, doctor, "PBE", test="potassium", value=6.2)

    res = await client.get("/api/portal/labs", params={"patient_id": "PBE"}, headers=ana)

    assert res.json()["patient_id"] == "PAN" and res.json()["labs"] == []
    assert len(await _labs(client, bea)) == 1


async def test_clinicians_and_anonymous_callers_are_refused(client, doctor, ana):
    assert (await client.get("/api/portal/labs")).status_code == 401
    assert (await client.get("/api/portal/labs", headers=doctor)).status_code in (401, 403)


async def test_the_patients_reads_are_audited(client, doctor, ana, db_session):
    await client.get("/api/portal/labs", headers=ana)

    rows = (await db_session.execute(select(PhiAccessLog))).scalars().all()
    assert [(r.patient_id, r.method) for r in rows if r.route == "/api/portal/labs"] == [("PAN", "GET")]


# --- the shares the portal already had --------------------------------------


async def test_the_portal_results_carry_the_structured_lab_and_opening_one_marks_it_read(client, doctor, ana):
    share_id = await _communicated(client, doctor, "PAN", reference_low=3.5, reference_high=5.1)

    listed = (await client.get("/api/results/shares", headers=ana)).json()
    assert listed[0]["lab"]["value"] == 6.2 and listed[0]["lab"]["viewed_at"] is None

    opened = (await client.get(f"/api/results/shares/{share_id}", headers=ana)).json()
    assert opened["lab"]["test_name"] == "potassium" and opened["lab"]["standing"] == "needs_attention"
    assert (await _labs(client, ana))[0]["viewed_at"] is not None


async def test_a_share_that_is_not_a_lab_result_has_no_lab_block(client, doctor, ana, db_session):
    event = TimelineEvent(
        patient_id="PAN", date=datetime(2026, 10, 9).date(), type="lab", title="Panel renal"
    )
    db_session.add(event)
    await db_session.commit()
    res = await client.post(
        "/api/results/shares",
        json={"patient_id": "PAN", "timeline_event_id": event.id, "message": "Hola"},
        headers=doctor,
    )
    assert res.status_code == 201

    (shared,) = (await client.get("/api/results/shares", headers=ana)).json()

    assert shared["lab"] is None and shared["event"]["title"] == "Panel renal"
    assert await _labs(client, ana) == [], "a manual share has no structured result to show"


async def test_the_clinicians_view_of_shares_is_unchanged(client, doctor, ana):
    await _communicated(client, doctor, "PAN")

    (shared,) = (await client.get("/api/results/shares", params={"patient_id": "PAN"}, headers=doctor)).json()

    assert "lab" not in shared
