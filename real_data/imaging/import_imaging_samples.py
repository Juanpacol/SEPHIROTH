"""Links RSNA chest X-ray samples (fetched by `fetch_rsna_samples.py`,
never committed — see this directory's README for the license/setup
requirements) to real patients as `ImagingStudy` + `TimelineEvent`
(type="imaging") rows.

These are representative stand-in images, not each patient's own scan
(RSNA's public sample set has no relationship to the Synthea-imported
patients) — `finding_summary` says so explicitly, and nothing here
invents a clinical finding: studies are imported as `status="pending"`,
awaiting a real AI/human read, exactly like an imaging study that just
arrived in the system would be.

    PYTHONPATH=.:platform python3 real_data/imaging/import_imaging_samples.py

Idempotent: each (patient, sample file) pair gets a deterministic id, so
re-running never creates duplicate studies — safe to re-run after
fetching more samples or importing more patients.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import List

SAMPLES_DIR_DEFAULT = Path(__file__).parent / "samples"
_READABLE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Same namespace pattern as import_synthea.py's MedicationOrder ids —
# stable across re-runs.
_IMAGING_STUDY_NAMESPACE = uuid.UUID("9b6e9c9a-3c1a-4e9b-8f7a-6a5e4b3c2d10")


def _list_samples(samples_dir: Path) -> List[Path]:
    if not samples_dir.exists():
        return []
    return sorted(p for p in samples_dir.iterdir() if p.suffix.lower() in _READABLE_EXTENSIONS)


async def _link_samples_to_patients(samples_dir: Path) -> int:
    from sqlalchemy import select  # noqa: PLC0415

    from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
    from data.schemas import ImagingStudy, Patient, TimelineEvent  # noqa: PLC0415

    samples = _list_samples(samples_dir)
    if not samples:
        print(
            f"No sample images found in {samples_dir} — run fetch_rsna_samples.py first "
            "(requires your own Kaggle account/credentials; see this directory's README)."
        )
        return 0

    created = 0
    async with SessionLocal() as session:
        patients = (await session.scalars(select(Patient).order_by(Patient.id))).all()
        if not patients:
            print("No patients in the database — nothing to link samples to.")
            return 0

        for i, sample in enumerate(samples):
            patient = patients[i % len(patients)]
            study_id = str(uuid.uuid5(_IMAGING_STUDY_NAMESPACE, f"{patient.id}:{sample.name}"))

            existing = await session.get(ImagingStudy, study_id)
            if existing is not None:
                continue

            study_date = date.today()
            session.add(
                ImagingStudy(
                    id=study_id,
                    patient_id=patient.id,
                    modality="X-ray",
                    body_part="Chest",
                    study_date=study_date,
                    status="pending",
                    finding_summary=(
                        f"Representative RSNA chest X-ray sample ({sample.name}) linked for "
                        "demonstration — not this patient's own imaging study. Awaiting AI/human read."
                    ),
                    severity="none",
                )
            )
            session.add(
                TimelineEvent(
                    patient_id=patient.id,
                    date=study_date,
                    type="imaging",
                    title="Chest X-ray (representative sample)",
                    detail=f"Linked sample file: {sample.name} — see real_data/imaging/README.md",
                    ai_generated=False,
                )
            )
            created += 1

        if created:
            await session.commit()

    return created


def main() -> int:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Link RSNA imaging samples to real patients")
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR_DEFAULT)
    args = parser.parse_args()

    created = asyncio.run(_link_samples_to_patients(args.samples_dir))
    print(f"Linked {created} new imaging sample(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
