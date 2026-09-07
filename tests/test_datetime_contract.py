"""One rule for datetimes crossing the API boundary: an offset, or a 422.

The first class is a regression test for the worst defect this audit found.
`POST /api/scheduling/exceptions` — how a clinician blocks time for surgery —
did no timezone handling at all, so a block sent correctly as
`09:00:00-05:00` was stored as `09:00` and `expand_slots` offered the theatre
hours as free. Invisible on a UTC server, five hours wrong on the on-premise
deployment SPEC-022 made the default.

The last class is the one that keeps this from coming back: it walks every
request model in the API and fails on a `datetime` field no endpoint guards.

Verifies AC-027-01, AC-027-02, AC-027-03 (docs/specs/SPEC-027-hardening.md).
"""

import ast
import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.routers import result_reviews as results_module
from api.routers import scheduling as scheduling_module
from api.timeparse import require_aware
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import AvailabilityException, Patient

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTERS = REPO_ROOT / "platform/api/routers"

CREDS = {"email": "tz-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(scheduling_module.router, prefix="/api/scheduling")
    api.include_router(results_module.router, prefix="/api/results")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def headers(client):
    token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestTheHelper:
    def test_an_aware_value_is_converted_not_truncated(self):
        # Spelled explicitly rather than read from the host, so the test means
        # the same thing on a UTC CI runner and on a laptop in Bogotá.
        bogota = timezone(timedelta(hours=-5))
        stored = require_aware(datetime(2026, 9, 7, 9, 0, tzinfo=bogota), "start_at")

        assert stored == datetime(2026, 9, 7, 14, 0)
        assert stored.tzinfo is None, "storage is naive UTC everywhere (B-7)"

    def test_a_naive_value_is_refused_not_guessed(self):
        """`astimezone` on a naive value silently reads the *server's* zone.
        That is the whole defect, and refusing is the only honest answer."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            require_aware(datetime(2026, 9, 7, 9, 0), "start_at")

        assert exc.value.status_code == 422
        assert "start_at" in exc.value.detail

    def test_a_utc_value_survives_unchanged(self):
        stored = require_aware(datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc), "start_at")
        assert stored == datetime(2026, 9, 7, 9, 0)


class TestSchedulingExceptions:
    """AC-027-01, AC-027-02 — the defect this phase was worth doing for."""

    async def test_a_blocked_morning_is_stored_at_the_hour_it_was_sent(self, client, headers, db_session):
        """Sent 09:00 in Bogotá, so 14:00 UTC. Stored as 09:00, this endpoint
        blocked 04:00-07:00 local and left the surgery hours bookable."""
        res = await client.post(
            "/api/scheduling/exceptions",
            json={
                "start_at": "2026-09-07T09:00:00-05:00",
                "end_at": "2026-09-07T12:00:00-05:00",
                "kind": "block",
                "reason": "cirugía",
            },
            headers=headers,
        )

        assert res.status_code == 201
        row = (await db_session.scalars(select(AvailabilityException))).one()
        assert row.start_at == datetime(2026, 9, 7, 14, 0)
        assert row.end_at == datetime(2026, 9, 7, 17, 0)

    async def test_a_naive_block_is_refused(self, client, headers):
        res = await client.post(
            "/api/scheduling/exceptions",
            json={"start_at": "2026-09-07T09:00:00", "end_at": "2026-09-07T12:00:00", "kind": "block"},
            headers=headers,
        )

        assert res.status_code == 422
        assert "start_at" in res.json()["detail"]

    async def test_mixing_aware_and_naive_is_a_422_not_a_crash(self, client, headers):
        """It used to raise `TypeError: can't compare offset-naive and
        offset-aware datetimes` — an unhandled 500 on a well-formed request."""
        res = await client.post(
            "/api/scheduling/exceptions",
            json={
                "start_at": "2026-09-08T09:00:00-05:00",
                "end_at": "2026-09-08T12:00:00",
                "kind": "block",
            },
            headers=headers,
        )

        assert res.status_code == 422
        assert "end_at" in res.json()["detail"]

    async def test_the_ordering_check_still_applies_after_conversion(self, client, headers):
        """Both sides converted before comparing, so an end before a start is
        caught on the same clock."""
        res = await client.post(
            "/api/scheduling/exceptions",
            json={
                "start_at": "2026-09-07T12:00:00-05:00",
                "end_at": "2026-09-07T09:00:00-05:00",
                "kind": "block",
            },
            headers=headers,
        )

        assert res.status_code == 422
        assert "before" in res.json()["detail"]

    async def test_two_offsets_naming_the_same_instant_store_the_same_row(self, client, headers, db_session):
        """14:00Z and 09:00-05:00 are one moment. The API has to agree."""
        await client.post(
            "/api/scheduling/exceptions",
            json={
                "start_at": "2026-09-10T14:00:00+00:00",
                "end_at": "2026-09-10T15:00:00+00:00",
                "kind": "block",
            },
            headers=headers,
        )
        await client.post(
            "/api/scheduling/exceptions",
            json={
                "start_at": "2026-09-10T09:00:00-05:00",
                "end_at": "2026-09-10T10:00:00-05:00",
                "kind": "block",
            },
            headers=headers,
        )

        rows = (await db_session.scalars(select(AvailabilityException))).all()
        assert {r.start_at for r in rows} == {datetime(2026, 9, 10, 14, 0)}


class TestLabIntake:
    """`taken_at` is the idempotency key: two feeds disagreeing by five hours
    about one draw would produce two results and two inbox rows."""

    async def test_a_naive_draw_time_is_refused(self, client, headers, db_session):
        db_session.add(Patient(id="PTZ1", name="Ana", age=61, sex="F", medical_record_number="MRN-PTZ1"))
        await db_session.commit()

        res = await client.post(
            "/api/results/labs",
            json={
                "patient_id": "PTZ1",
                "test_name": "potassium",
                "value": 6.2,
                "taken_at": "2026-09-06T09:00:00",
            },
            headers=headers,
        )

        assert res.status_code == 422

    async def test_an_absent_draw_time_is_still_allowed(self, client, headers, db_session):
        """It defaults to now. Requiring an offset on a field nobody sent would
        break every caller that lets the server timestamp the row."""
        db_session.add(Patient(id="PTZ2", name="Beto", age=44, sex="M", medical_record_number="MRN-PTZ2"))
        await db_session.commit()

        res = await client.post(
            "/api/results/labs",
            json={"patient_id": "PTZ2", "test_name": "potassium", "value": 4.1},
            headers=headers,
        )

        assert res.status_code == 201


class TestTheContractIsUniform:
    """AC-027-03. A structural check, like the PHI-seam one (ADR-015): a
    `datetime` field nobody guards is a field that silently stores the wrong
    hour, and that is exactly what this phase found."""

    #: Fields whose handler is expected to guard them.
    def _datetime_request_fields(self):
        found = {}
        for path in sorted(ROUTERS.glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases):
                    continue
                for item in node.body:
                    if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                        continue
                    annotation = ast.unparse(item.annotation)
                    if "datetime" in annotation and "date]" not in annotation:
                        found.setdefault(path.stem, set()).add(item.target.id)
        return found

    def test_every_datetime_request_field_is_guarded(self):
        unguarded = []
        for module, fields in self._datetime_request_fields().items():
            source = (ROUTERS / f"{module}.py").read_text()
            for field in sorted(fields):
                guarded = re.search(rf"(require_aware|optional_aware)\(\s*body\.{field}\b", source)
                if not guarded:
                    unguarded.append(f"{module}.{field}")

        assert not unguarded, (
            "these request fields accept a datetime and never pass it through the "
            f"contract: {unguarded}. Use `require_aware` / `optional_aware` "
            "(platform/api/timeparse.py) — a naive value stored as-is is the wrong hour."
        )

    def test_the_helper_is_what_they_all_use(self):
        """Five endpoints had this logic inline, five times, and the sixth had
        none. One function is what makes 'everywhere' checkable."""
        source = (ROUTERS / "scheduling.py").read_text()

        assert "require_aware(" in source
        assert "must be timezone-aware" not in source, "an inline copy came back"
