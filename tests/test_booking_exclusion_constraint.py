"""Verifies the Postgres-only `EXCLUDE USING gist` constraint
(`ck_appointments_no_overlap`, added in
`migrations/versions/32a957e66854_double_booking_exclusion_constraint.py`)
actually backstops the race the app-level SELECT-then-check in
`book_appointment`/`update_appointment` can miss — two unlocked queries,
no row locking. Bypasses the API/app-level check entirely (writes
straight to the DB from two independent sessions) to simulate exactly
that race.

Skips automatically when no local Postgres is reachable — same pattern as
`tests/test_alembic_migration.py`. Never touches the shared local
database's persistent state beyond its own rows (unique ids per test
run), and does not run migrations — it assumes `alembic upgrade head` has
already been applied (same assumption as `test_alembic_migration.py`).
"""

import socket
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from data.schemas import Appointment, Patient, User

LOCAL_POSTGRES_HOST = "localhost"
LOCAL_POSTGRES_PORT = 5433
LOCAL_POSTGRES_URL = (
    f"postgresql+asyncpg://clinical_ai:clinical_ai_password@"
    f"{LOCAL_POSTGRES_HOST}:{LOCAL_POSTGRES_PORT}/clinical_ai_db"
)


def _local_postgres_reachable() -> bool:
    try:
        with socket.create_connection((LOCAL_POSTGRES_HOST, LOCAL_POSTGRES_PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _local_postgres_reachable(),
        reason=(
            f"no Postgres reachable at {LOCAL_POSTGRES_HOST}:{LOCAL_POSTGRES_PORT} — "
            "run `docker compose up -d postgres` and `alembic upgrade head`"
        ),
    ),
]


@pytest_asyncio.fixture
async def pg_sessionmaker():
    engine = create_async_engine(LOCAL_POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_exclusion_constraint_rejects_a_race_the_app_check_would_miss(pg_sessionmaker):
    async with pg_sessionmaker() as setup:
        clinician = User(
            id="EXCL-CLIN-1",
            email="excl-clin-1@example.org",
            name="Dr. Exclusion",
            hashed_password="x",
            role="clinician",
        )
        patient_a = Patient(id="EXCL-PAT-A", name="A", age=30, sex="M", medical_record_number="EXCL-MRN-A")
        patient_b = Patient(id="EXCL-PAT-B", name="B", age=31, sex="F", medical_record_number="EXCL-MRN-B")
        setup.add_all([clinician, patient_a, patient_b])
        await setup.commit()

    try:
        start = datetime(2031, 3, 3, 9, 0)
        end = datetime(2031, 3, 3, 9, 30)

        # Session 1: simulates the first request having already passed its
        # app-level SELECT-then-check (no row exists yet) and now writing.
        async with pg_sessionmaker() as s1:
            s1.add(
                Appointment(
                    id="EXCL-APPT-1",
                    clinician_id=clinician.id,
                    patient_id=patient_a.id,
                    start_at=start,
                    end_at=end,
                    status="booked",
                )
            )
            await s1.commit()

        # Session 2: simulates a second, concurrent request that ran its
        # own SELECT-then-check *before* session 1's commit landed — the
        # exact TOCTOU window `book_appointment` has today (no row
        # locking) — and now also tries to write an overlapping slot.
        with pytest.raises(IntegrityError):
            async with pg_sessionmaker() as s2:
                s2.add(
                    Appointment(
                        id="EXCL-APPT-2",
                        clinician_id=clinician.id,
                        patient_id=patient_b.id,
                        start_at=start,
                        end_at=end,
                        status="booked",
                    )
                )
                await s2.commit()
    finally:
        async with pg_sessionmaker() as cleanup:
            for appt_id in ("EXCL-APPT-1", "EXCL-APPT-2"):
                appt = await cleanup.get(Appointment, appt_id)
                if appt is not None:
                    await cleanup.delete(appt)
            for patient_id in ("EXCL-PAT-A", "EXCL-PAT-B"):
                patient = await cleanup.get(Patient, patient_id)
                if patient is not None:
                    await cleanup.delete(patient)
            user = await cleanup.get(User, "EXCL-CLIN-1")
            if user is not None:
                await cleanup.delete(user)
            await cleanup.commit()
