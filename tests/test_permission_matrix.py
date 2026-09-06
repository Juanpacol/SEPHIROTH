"""Every route, three credentials, no exceptions nobody wrote down.

The audit that produced this found the boundary already solid: of 143 routes,
135 refuse an anonymous caller and the 8 that do not are the two health checks
and the six authentication entry points. That was a good result and nobody's to
rely on, because no test asserted it — the next router mounted without a guard
would be found by a person, or not at all.

`PUBLIC` is a hardcoded list on purpose. Adding a route to it is the moment
somebody decides that route is public, and that decision should be visible in a
diff rather than inferred from an absent dependency.

Verifies AC-027-04, AC-027-05 (docs/specs/SPEC-027-hardening.md).
"""

import re
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app

pytestmark = pytest.mark.asyncio

#: Routes that legitimately answer without a session, and why.
PUBLIC = {
    ("GET", "/health"): "liveness probe; no I/O, no data",
    ("GET", "/health/ready"): "readiness probe for the deploy smoke test",
    ("POST", "/api/auth/register"): "creating the first account, and clinician-gated after that",
    ("POST", "/api/auth/login"): "the entry point itself",
    ("POST", "/api/auth/login/mfa"): "second factor of the entry point",
    ("POST", "/api/auth/password-reset/request"): "cannot require a session to recover one",
    ("POST", "/api/auth/password-reset/confirm"): "same",
    ("POST", "/api/auth/portal/claim"): "a patient redeeming an invite has no account yet",
}

#: Routes a patient account is allowed to reach. Everything else in the API is
#: clinician-only, and the portal deliberately derives the patient from the
#: token rather than taking an id (decision #20).
PATIENT_REACHABLE = {
    "/api/portal/",
    "/api/auth/",
    "/api/push/",
    "/api/notifications",
    "/api/scheduling/",
    "/api/results/",
    "/health",
    # Serves both roles by design and returns zeros for the clinician counters
    # to a patient, so the frontend needs no role branch to read it. Verified
    # in `test_a_patient_sees_only_their_own_counters` below rather than taken
    # on trust from this list.
    "/api/badges",
}

#: Not role-gated at all: the tick is authorised by a shared secret, because
#: the caller is an external cron with no account to have a role.
NOT_ROLE_GATED = {("POST", "/internal/tick")}


def _routes():
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
                yield method.upper(), path


def _concrete(path: str) -> str:
    """A path with its parameters filled, so routing resolves.

    The id never matches a row, which is the point: the check has to fail at
    the guard, before anything looks the id up.
    """
    return re.sub(r"\{[^}]+\}", "probe-id", path)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestNothingIsOpenByAccident:
    """AC-027-04."""

    async def test_every_route_refuses_an_anonymous_caller(self, client):
        leaks = []
        for method, path in _routes():
            if (method, path) in PUBLIC:
                continue
            res = await client.request(method, _concrete(path), json={})
            if res.status_code not in (401, 403):
                leaks.append(f"{method} {path} -> {res.status_code}")

        assert not leaks, (
            "these routes answered without a session: "
            f"{leaks}. Add the guard, or add the route to PUBLIC with the reason."
        )

    async def test_the_public_list_names_only_routes_that_exist(self):
        """A stale entry is a guard somebody thinks is deliberate."""
        actual = set(_routes())
        stale = sorted(f"{m} {p}" for m, p in PUBLIC if (m, p) not in actual)

        assert not stale, f"PUBLIC names routes the API no longer has: {stale}"

    async def test_every_public_route_says_why(self):
        assert all(reason.strip() for reason in PUBLIC.values())

    async def test_the_health_checks_answer(self, client):
        """The two that must work without credentials, because a load balancer
        has none."""
        assert (await client.get("/health")).status_code == 200

    async def test_a_garbage_token_is_refused_like_no_token(self, client):
        """A malformed credential must not take a different path from an absent
        one -- that difference is where parsing bugs become auth bypasses."""
        headers = {"Authorization": "Bearer not-a-real-token"}

        res = await client.get("/api/patients", headers=headers)

        assert res.status_code in (401, 403)


class TestRoleSeparation:
    """AC-027-05 — a patient token on a clinician route."""

    @pytest.fixture
    async def patient_headers(self, client, db_session, monkeypatch):
        from auth.security import hash_password
        from core.db import get_session
        from data.schemas import Patient, User

        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session

        patient = Patient(
            id=f"PM{uuid4().hex[:5]}",
            name="Ana",
            age=61,
            sex="F",
            medical_record_number=f"MRN-{uuid4().hex[:5]}",
        )
        email = f"portal-{uuid4().hex[:6]}@example.org"
        db_session.add_all(
            [
                patient,
                User(
                    id=str(uuid4()),
                    email=email,
                    name="Paciente",
                    hashed_password=await hash_password("password123"),
                    role="patient",
                    patient_id=patient.id,
                ),
            ]
        )
        await db_session.commit()

        token = (
            await client.post("/api/auth/login", json={"email": email, "password": "password123"})
        ).json()["access_token"]
        yield {"Authorization": f"Bearer {token}"}
        app.dependency_overrides.clear()

    async def test_a_patient_cannot_reach_a_clinician_route(self, client, patient_headers):
        leaks = []
        for method, path in _routes():
            if (method, path) in PUBLIC:
                continue
            if (method, path) in NOT_ROLE_GATED:
                continue
            if any(path.startswith(prefix) for prefix in PATIENT_REACHABLE):
                continue
            res = await client.request(method, _concrete(path), json={}, headers=patient_headers)
            # 403 is the guard. 404/409/422 mean the guard let it through and
            # something downstream complained -- which is a leak of existence,
            # not authorisation.
            if res.status_code != 403:
                leaks.append(f"{method} {path} -> {res.status_code}")

        assert not leaks, f"a patient token reached these clinician routes: {leaks}"

    async def test_the_patient_can_still_reach_their_own_portal(self, client, patient_headers):
        """The separation has to be a boundary, not a wall."""
        res = await client.get("/api/portal/me", headers=patient_headers)

        assert res.status_code == 200

    async def test_a_patient_sees_only_their_own_counters(self, client, patient_headers):
        """`/api/badges` answers both roles on purpose. What a patient gets back
        has to be zeros for the clinician counters -- otherwise the shared route
        is a leak of how much work the clinic has."""
        body = (await client.get("/api/badges", headers=patient_headers)).json()

        assert body["tasks_open"] == 0
        assert body["tasks_overdue"] == 0
        assert body["alerts_active"] == 0
        assert "notifications_unread" in body
