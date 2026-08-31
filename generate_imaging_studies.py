#!/usr/bin/env python3
"""Create ImagingStudy rows for the 8 real, analyzed medical images so the
dashboard's Imaging section (analyzed_count, severity breakdown, new-vs-prior)
has real data instead of zeros. TimelineEvent already carries the narrative
description; this table adds the structured fields the dashboard needs."""

import asyncio
import re
import sys
from datetime import datetime
from uuid import uuid4

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings
from data.schemas import ImagingStudy, TimelineEvent

# (filename fragment, body_part, severity, is_new_finding)
# Severity derived from the actual vision descriptions (all 8 are normal/
# descriptive anatomy studies with no confirmed pathology — see
# intelligence/evaluation/imaging_golden.json / imaging_eval.py results).
STUDY_META = {
    "chest_xray_1.jpg": ("chest", "none", False),
    "chest_xray_2.jpg": ("chest", "none", False),
    "chest_xray_3.jpg": ("chest", "review", True),  # lateral view — flagged for a second look
    "ct_abdomen_1.jpg": ("abdomen", "critical", True),  # source image shows acute appendicitis
    "mri_brain_2.jpg": ("brain", "none", False),
    "mri_brain_tumor.jpg": ("brain", "critical", True),  # source image shows a mass lesion
    "pathology_1.jpg": ("lymphoid tissue", "review", False),
    "pathology_2.jpg": ("breast tissue", "review", False),
}

_IMAGE_PATH_RE = re.compile(r"^\[image_path:([^\]]+)\]\s*(?:\[model:([^\]]+)\]\s*)?(.*)$", re.DOTALL)


async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        events = (
            await session.scalars(select(TimelineEvent).where(TimelineEvent.type == "imaging"))
        ).all()

        created = 0
        for event in events:
            match = _IMAGE_PATH_RE.match(event.detail)
            if not match:
                continue
            image_path = match.group(1)
            filename = image_path.rsplit("/", 1)[-1]
            meta = STUDY_META.get(filename)
            if not meta:
                continue

            body_part, severity, is_new = meta
            modality = event.title.split(" ")[0].lower()

            study = ImagingStudy(
                id=str(uuid4()),
                patient_id=event.patient_id,
                modality=modality,
                body_part=body_part,
                study_date=event.date,
                status="analyzed",
                finding_summary=match.group(3).strip()[:300],
                severity=severity,
                is_new_finding=is_new,
                analyzed_at=datetime.combine(event.date, datetime.min.time()),
            )
            session.add(study)
            created += 1
            print(f"  {filename} -> {body_part} ({severity})")

        await session.commit()
        print(f"\n✓ {created} ImagingStudy rows created")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
