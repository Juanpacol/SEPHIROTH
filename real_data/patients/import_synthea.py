"""
Parse Synthea CSV exports into `Patient`/`TimelineEvent` records matching
the schema in `data/schemas/__init__.py`, and optionally insert them into
the database alongside the two demo patients (`platform/core/db.py::
SEED_PATIENTS`, which this script never touches or duplicates).

The parsing logic (`parse_patients`) is pure and side-effect-free — it's
what `tests/test_real_data_patients.py` exercises against tiny inline
fixture CSVs, never against a live download. `main()` (network + DB) is
for manual use only:

    PYTHONPATH=.:platform python3 real_data/patients/import_synthea.py \
        --raw-dir real_data/patients/synthea_raw --limit 25

Requires `real_data/patients/synthea_raw/*.csv` to already exist — run
`fetch_synthea_sample.py` first.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

RAW_DIR_DEFAULT = Path(__file__).parent / "synthea_raw"

# Synthea appends a numeric disambiguator to generated names (e.g.
# "Gregg522"); strip it for display.
_NAME_SUFFIX_RE = re.compile(r"\d+$")

# A handful of common LOINC-coded observations worth surfacing in the
# free-form `lab_results` field — matches the style of the existing demo
# patients (SEED_PATIENTS in platform/core/db.py), which use a few
# human-readable key labs rather than every observation ever recorded.
_LAB_CODES = {
    "4548-4": "hba1c",  # Hemoglobin A1c
    "2093-3": "cholesterol",
    "18262-6": "ldl",
    "8480-6": "bp_systolic",
    "8462-4": "bp_diastolic",
    "39156-5": "bmi",
}


@dataclass
class ParsedPatient:
    id: str
    name: str
    age: int
    sex: str
    medical_record_number: str
    conditions: List[str] = field(default_factory=list)
    medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    lab_results: Dict[str, str] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)


def _clean_name(raw: str) -> str:
    return _NAME_SUFFIX_RE.sub("", raw)


_NON_NAME_TOKENS = {"hr", "er", "xr", "sr", "ml", "mg", "mcg", "unt"}


def _generic_drug_name(description: str) -> str:
    """Synthea medication descriptions are dispensable-product strings
    (e.g. "amLODIPine 2.5 MG Oral Tablet", "24 HR Metformin hydrochloride
    500 MG Extended Release Oral Tablet") — take the first alphabetic,
    non-formulation token as the generic name, matching the plain generic
    names the rest of the app uses
    (`intelligence/mcp/drug_safety_server.py::find_interactions`)."""
    for token in description.split():
        cleaned = token.strip().lower()
        if cleaned.isalpha() and cleaned not in _NON_NAME_TOKENS:
            return cleaned
    return description.split()[0].strip().lower()  # fallback: shouldn't normally hit


def _compute_age(birthdate: str, as_of: date) -> int:
    year, month, day = (int(p) for p in birthdate.split("-"))
    born = date(year, month, day)
    return as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def parse_patients(
    raw_dir: Path,
    patient_ids: Optional[List[str]] = None,
    as_of: Optional[date] = None,
    max_timeline_events: int = 12,
) -> List[ParsedPatient]:
    """Pure parsing: reads `patients.csv`, `conditions.csv`,
    `medications.csv`, `allergies.csv`, and (if present) `observations.csv`
    from `raw_dir`, and returns one `ParsedPatient` per row in
    `patients.csv` (optionally filtered to `patient_ids`).

    No I/O beyond reading these files, no database access — fully testable
    against tiny fixture CSVs.
    """
    as_of = as_of or datetime.now().date()

    patients_rows = _read_csv(raw_dir / "patients.csv")
    if patient_ids is not None:
        wanted = set(patient_ids)
        patients_rows = [r for r in patients_rows if r["Id"] in wanted]

    conditions_by_patient: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in _read_csv(raw_dir / "conditions.csv"):
        conditions_by_patient[row["PATIENT"]].append(row)

    medications_by_patient: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in _read_csv(raw_dir / "medications.csv"):
        medications_by_patient[row["PATIENT"]].append(row)

    allergies_by_patient: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    allergies_path = raw_dir / "allergies.csv"
    if allergies_path.exists():
        for row in _read_csv(allergies_path):
            allergies_by_patient[row["PATIENT"]].append(row)

    labs_by_patient: Dict[str, Dict[str, str]] = defaultdict(dict)
    observations_path = raw_dir / "observations.csv"
    if observations_path.exists():
        for row in _read_csv(observations_path):
            label = _LAB_CODES.get(row.get("CODE", ""))
            if label and row.get("VALUE"):
                units = row.get("UNITS", "")
                labs_by_patient[row["PATIENT"]][label] = f"{row['VALUE']}{units and ' ' + units}"

    results: List[ParsedPatient] = []
    for row in patients_rows:
        pid = row["Id"]
        conditions = conditions_by_patient.get(pid, [])
        medications = medications_by_patient.get(pid, [])
        allergies = allergies_by_patient.get(pid, [])

        timeline: List[Dict[str, Any]] = []
        for c in conditions:
            if not c.get("START"):
                continue
            timeline.append(
                {"date": c["START"][:10], "type": "diagnosis", "title": c["DESCRIPTION"], "detail": ""}
            )
        for m in medications:
            if not m.get("START"):
                continue
            generic = _generic_drug_name(m["DESCRIPTION"])
            timeline.append(
                {
                    "date": m["START"][:10],
                    "type": "medication",
                    "title": f"Started {generic}",
                    "detail": m["DESCRIPTION"],
                }
            )
        timeline.sort(key=lambda e: e["date"])
        timeline = timeline[:max_timeline_events]

        results.append(
            ParsedPatient(
                id=pid,
                name=f"{_clean_name(row['FIRST'])} {_clean_name(row['LAST'])}",
                age=_compute_age(row["BIRTHDATE"], as_of),
                sex=row["GENDER"],
                medical_record_number=f"SYN-{pid[:8].upper()}",
                conditions=sorted({c["DESCRIPTION"] for c in conditions}),
                medications=sorted({_generic_drug_name(m["DESCRIPTION"]) for m in medications}),
                allergies=sorted({a["DESCRIPTION"] for a in allergies}),
                lab_results=dict(labs_by_patient.get(pid, {})),
                timeline=timeline,
            )
        )
    return results


async def _insert_into_db(parsed: List[ParsedPatient]) -> None:
    """Manual-use only: inserts alongside the existing demo patients.
    Never called from tests or CI."""
    from datetime import date as date_cls

    from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
    from data.schemas import Patient, TimelineEvent  # noqa: PLC0415

    async with SessionLocal() as session:
        for p in parsed:
            session.add(
                Patient(
                    id=p.id,
                    name=p.name,
                    age=p.age,
                    sex=p.sex[:1],
                    medical_record_number=p.medical_record_number,
                    conditions=p.conditions,
                    medications=p.medications,
                    allergies=p.allergies,
                    lab_results=p.lab_results,
                )
            )
            for event in p.timeline:
                session.add(
                    TimelineEvent(
                        patient_id=p.id,
                        date=date_cls.fromisoformat(event["date"]),
                        type=event["type"],
                        title=event["title"][:200],
                        detail=event["detail"],
                        ai_generated=False,
                    )
                )
        await session.commit()


def main() -> int:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Import a Synthea sample into the SEPHIROTH database")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR_DEFAULT)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    if not args.raw_dir.exists():
        print(f"{args.raw_dir} not found — run fetch_synthea_sample.py first.")
        return 1

    all_patients = parse_patients(args.raw_dir)
    subset = all_patients[: args.limit]
    print(f"Parsed {len(all_patients)} patients from {args.raw_dir}, importing {len(subset)}.")
    asyncio.run(_insert_into_db(subset))
    print(f"Inserted {len(subset)} Synthea patients (alongside P001/P002).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
