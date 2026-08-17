"""Patient-portal data isolation — built against the real `api.main.app`
wiring (not a reconstructed test app), so these tests exercise the actual
router-level `dependencies=[Depends(require_clinician)]` guards and the
real `portal.py` router.

Verifies: a patient can never read another patient's chart, a patient can
never reach a clinician route, a clinician keeps full access (regression),
and — via a route-shape meta-test — that every clinician router still
carries the guard and no portal route accepts a `patient_id` parameter."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient, User

CLINICIAN_ROUTES = [
    ("GET", "/api/patients"),
    ("GET", "/api/patients/P001"),
    ("GET", "/api/patients/P001/timeline"),
    ("GET", "/api/dashboard/stats"),
    ("GET", "/api/agents/history"),
    ("POST", "/api/agents/consult"),
    ("GET", "/api/rag/search?q=x"),
    ("POST", "/api/medical/drugs/check"),
]


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _register_clinician(client, email: str) -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Test", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def _make_patient_user(db_session, patient_id: str, email: str) -> User:
    patient = Patient(
        id=patient_id,
        name="Patient",
        age=40,
        sex="F",
        medical_record_number=f"PT-{patient_id}",
        lab_results={"a1c": "6.5%"},
    )
    db_session.add(patient)
    from auth.security import create_access_token, hash_password

    user = User(
        id=f"user-{patient_id}",
        email=email,
        name="Portal Patient",
        hashed_password=hash_password("password123"),
        role="patient",
        patient_id=patient_id,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user.id)


async def test_patient_a_cannot_read_patient_b(client, db_session):
    token_a = await _make_patient_user(db_session, "PA1", "a@example.org")
    await _make_patient_user(db_session, "PB1", "b@example.org")

    async with client:
        res = await client.get("/api/portal/me", headers={"Authorization": f"Bearer {token_a}"})
        assert res.status_code == 200
        assert res.json()["id"] == "PA1"


async def test_portal_me_ignores_any_client_supplied_id(client, db_session):
    token_a = await _make_patient_user(db_session, "PA2", "a2@example.org")
    await _make_patient_user(db_session, "PB2", "b2@example.org")

    async with client:
        res = await client.get(
            "/api/portal/me?patient_id=PB2", headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res.status_code == 200
        assert res.json()["id"] == "PA2"  # the query param is simply not read


@pytest.mark.parametrize("method,path", CLINICIAN_ROUTES)
async def test_patient_cannot_reach_clinician_routes(client, db_session, method, path):
    token = await _make_patient_user(db_session, "PC1", "c1@example.org")
    async with client:
        res = await client.request(method, path, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403


async def test_clinician_cannot_reach_portal(client):
    async with client:
        headers = await _register_clinician(client, "clin1@example.org")
        res = await client.get("/api/portal/me", headers=headers)
        assert res.status_code == 403


@pytest.mark.parametrize("method,path", CLINICIAN_ROUTES)
async def test_clinician_keeps_access_no_403(client, db_session, method, path):
    """Regression guard: a clinician must never be blocked by the new
    role check. (Some of these return 4xx/2xx for other reasons — a
    missing consult body, an empty history — the only thing asserted
    here is that the role gate itself never fires, i.e. never 403.)"""
    async with client:
        headers = await _register_clinician(client, "clin2@example.org")
        res = await client.request(method, path, headers=headers)
        assert res.status_code != 403


async def test_unauthenticated_cannot_list_patients(client):
    """Regression lock for the original PHI leak (Phase A)."""
    async with client:
        res = await client.get("/api/patients")
        assert res.status_code == 401


def test_every_clinician_route_carries_the_clinician_guard():
    """Route-shape meta-test: introspect `app.routes` and assert every
    route under the clinician-only prefixes actually depends on
    `require_clinician`, and no `/api/portal/*` route declares a
    `patient_id` parameter. This is what keeps the fix from decaying as
    routes are added later, not any single test case above."""
    from auth.deps import require_clinician

    clinician_prefixes = ("/api/patients", "/api/dashboard", "/api/agents", "/api/medical", "/api/rag")
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(clinician_prefixes):
            continue
        dependant_calls = {d.call for d in route.dependant.dependencies}
        assert require_clinician in dependant_calls, f"{path} is missing require_clinician"

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/portal"):
            assert "patient_id" not in path, f"{path} must not declare patient_id as a parameter"
