#!/usr/bin/env python3
"""One-time backfill: create the `ResultReview` every existing `LabResult`/
`ImagingStudy` row should already have.

`real_data/patients/import_synthea.py` and
`real_data/imaging/import_imaging_samples.py` used to insert those rows
directly (`session.add(LabResult(...))`), bypassing
`result_service.record_lab_result`/`record_imaging_study` — the only
functions that also classify severity and create the review. Both import
scripts are now fixed to go through the service for anything imported from
now on; this script catches up everything they already wrote before that
fix, using the same `classify_lab`/`classify_imaging` functions so a
backfilled review is classified identically to one made live.

Batched rather than one review per round-trip (which timed out against
Supabase's pooler on ~4,700 rows held in one long-running transaction):
existing `(result_type, result_id)` pairs are loaded once into a set, then
new reviews are added and committed in chunks.

Idempotent: skips any pair already in that set, so re-running after a
partial run or a fresh import only fills the gap.

Usage:
    PYTHONPATH=.:platform .venv/bin/python scripts/backfill_result_reviews.py [--dry-run]
"""

import argparse
import asyncio
import sys
from uuid import uuid4

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from sqlalchemy import select

from core.db import SessionLocal
from data.schemas import ImagingStudy, LabResult, ResultReview
from sephiroth.clinical.results import classify_imaging, classify_lab

_BATCH_SIZE = 50


async def main(dry_run: bool) -> None:
    async with SessionLocal() as session:
        existing = set(
            (await session.execute(select(ResultReview.result_type, ResultReview.result_id))).all()
        )

        labs = (await session.scalars(select(LabResult))).all()
        studies = (await session.scalars(select(ImagingStudy))).all()

        labs_created = 0
        pending = 0
        for lab in labs:
            if ("lab", str(lab.id)) in existing:
                continue
            classification = classify_lab(
                lab.test_name, lab.value, reference_low=lab.reference_low, reference_high=lab.reference_high
            )
            if not dry_run:
                session.add(
                    ResultReview(
                        id=str(uuid4()),
                        result_type="lab",
                        result_id=str(lab.id),
                        patient_id=lab.patient_id,
                        status="received",
                        severity=classification.severity,
                        classification_reason=classification.reason[:300],
                        created_at=lab.taken_at,
                        updated_at=lab.taken_at,
                    )
                )
                pending += 1
                if pending >= _BATCH_SIZE:
                    await session.commit()
                    pending = 0
            labs_created += 1

        studies_created = 0
        for study in studies:
            if ("imaging", study.id) in existing:
                continue
            classification = classify_imaging(study.severity, study.finding_summary or "")
            if not dry_run:
                moment = study.analyzed_at or study.created_at
                session.add(
                    ResultReview(
                        id=str(uuid4()),
                        result_type="imaging",
                        result_id=study.id,
                        patient_id=study.patient_id,
                        status="received",
                        severity=classification.severity,
                        classification_reason=classification.reason[:300],
                        created_at=moment,
                        updated_at=moment,
                    )
                )
                pending += 1
                if pending >= _BATCH_SIZE:
                    await session.commit()
                    pending = 0
            studies_created += 1

        if dry_run:
            await session.rollback()
            print(f"[dry-run] would create {labs_created} lab reviews, {studies_created} imaging reviews")
        else:
            if pending:
                await session.commit()
            print(f"created {labs_created} lab reviews, {studies_created} imaging reviews")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be created, write nothing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
