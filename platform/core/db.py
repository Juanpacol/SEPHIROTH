"""Async database engine, session dependency, and startup seeding."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from data.schemas import Base, Patient, TimelineEvent
from sephiroth.safety.alerts import generate_alerts_for_all_patients

logger = logging.getLogger(__name__)

_ALEMBIC_INI_PATH = Path(__file__).parent.parent.parent / "alembic.ini"

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with SessionLocal() as session:
        yield session


SEED_PATIENTS = [
    {
        "patient": Patient(
            id="P001",
            name="Mohamed Ahmed",
            age=52,
            sex="M",
            medical_record_number="PT-20458",
            conditions=["Type 2 Diabetes", "Hypertension"],
            medications=["metformin", "lisinopril"],
            allergies=["penicillin"],
            lab_results={"hba1c": "6.8%", "bp": "138/86", "ldl": "102 mg/dL"},
        ),
        "timeline": [
            ("2021-03-10", "diagnosis", "Type 2 Diabetes diagnosed", "HbA1c 9.2%"),
            ("2021-03-15", "medication", "Started metformin", "1000mg BID"),
            ("2021-09-20", "lab", "HbA1c improved", "HbA1c 6.8%"),
            ("2023-01-05", "diagnosis", "Hypertension diagnosed", "BP 152/95"),
            ("2023-01-05", "medication", "Started lisinopril", "10mg daily"),
            ("2026-04-13", "imaging", "Chest CT", "Lung capacity efficiency 79%, moderate risk"),
        ],
    },
    {
        "patient": Patient(
            id="P002",
            name="Layla Al-Hakim",
            age=68,
            sex="F",
            medical_record_number="PT-20973",
            conditions=["Heart Failure (HFrEF)", "Atrial Fibrillation"],
            medications=["warfarin", "furosemide", "digoxin"],
            allergies=[],
            lab_results={"bnp": "450 pg/mL", "ef": "35%", "inr": "2.4", "potassium": "3.4 mEq/L"},
        ),
        "timeline": [
            ("2024-06-02", "diagnosis", "HFrEF diagnosed", "EF 35%"),
            ("2024-06-10", "medication", "Started furosemide + digoxin", ""),
            ("2025-11-22", "event", "Hospitalization", "Acute decompensation"),
            ("2025-12-01", "event", "Discharged", "Stable on optimized therapy"),
        ],
    },
]


def _run_alembic_upgrade() -> None:
    """Sync entry point for Alembic's `upgrade head` — runs its own
    async engine internally (see migrations/env.py), so this must be
    called off the running event loop (via asyncio.to_thread), not
    nested inside it: `env.py`'s `asyncio.run(...)` would otherwise
    raise "cannot be called from a running event loop"."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.attributes["configure_logger"] = False  # app already configured logging
    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Create/upgrade the schema and seed demo patients when the table is
    empty (idempotent).

    Postgres (local docker-compose or Supabase): schema is Alembic-managed
    — `migrations/versions/` is the single source of truth, applied via
    `alembic upgrade head` on every boot (safe to run repeatedly; a no-op
    once already current). SQLite (tests, `tests/conftest.py::db_session`)
    has no migration history and never will — `Base.metadata.create_all`
    there is the accepted, ephemeral-schema pattern for a per-test DB.
    """
    if engine.dialect.name == "postgresql":
        await asyncio.to_thread(_run_alembic_upgrade)
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = await session.scalar(select(Patient.id).limit(1))
        if not existing:
            for entry in SEED_PATIENTS:
                session.add(entry["patient"])
                for event_date, event_type, title, detail in entry["timeline"]:
                    session.add(
                        TimelineEvent(
                            patient_id=entry["patient"].id,
                            date=date.fromisoformat(event_date),
                            type=event_type,
                            title=title,
                            detail=detail,
                        )
                    )
            await session.commit()
            logger.info("Seeded %d demo patients", len(SEED_PATIENTS))

        # Idempotent: only creates an Alert for a risk flag that doesn't
        # already have an open one, so this is safe to run on every boot
        # and automatically covers patients imported outside the seed path
        # (e.g. real_data/patients/import_synthea.py).
        await generate_alerts_for_all_patients(session)
