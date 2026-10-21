"""Adds the bundled demo imaging analyses to the database, so the Imaging page's
"Recent imaging analyses" has studies whose image ships with the deployment.

    PYTHONPATH=.:platform .venv/bin/python scripts/seed_imaging_demo.py

Each analysis (`platform/api/static/imaging-demo/analyses.json`, written by
`generate_imaging_demo.py`) becomes one `TimelineEvent` of type "imaging" on one
existing patient, using the `[image_path:...] [model:...] text` convention the
page already parses, with the image named `demo:<file>`. They are stand-ins, not
that patient's own scan, and the card says they are AI-generated.

Idempotent: a patient already holding a demo event for a file is skipped, so it
is safe to re-run. Needs at least as many patients as there are demo studies, and
only ever adds rows: it never edits or deletes one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Patient, TimelineEvent

DEMO_DIR = Path(__file__).resolve().parents[1] / "platform" / "api" / "static" / "imaging-demo"


def load_analyses() -> list[dict]:
    return json.loads((DEMO_DIR / "analyses.json").read_text())


async def seed(session: AsyncSession, today: date | None = None) -> int:
    """Insert the missing demo events. Returns how many were added."""
    analyses = load_analyses()
    patients = (
        (await session.execute(select(Patient).order_by(Patient.id).limit(len(analyses)))).scalars().all()
    )
    added = 0
    for analysis, patient in zip(analyses, patients):
        marker = f"[image_path:demo:{analysis['file']}]"
        taken = await session.scalar(
            select(TimelineEvent.id)
            .where(TimelineEvent.type == "imaging", TimelineEvent.detail.startswith(marker))
            .limit(1)
        )
        if taken is not None:
            continue
        session.add(
            TimelineEvent(
                patient_id=patient.id,
                date=today or date.today(),
                type="imaging",
                title=f"{analysis['modality']} vision description",
                detail=f"{marker} [model:{analysis['model']}] {analysis['description']}",
                ai_generated=True,
            )
        )
        added += 1
    await session.commit()
    return added


async def main() -> None:
    from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    async with SessionLocal() as session:
        print(f"added {await seed(session)} demo imaging analyses")


if __name__ == "__main__":
    asyncio.run(main())
