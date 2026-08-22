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
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

RAW_DIR_DEFAULT = Path(__file__).parent / "synthea_raw"

# Deterministic namespace for MedicationOrder ids (uuid5 of patient+drug
# code+start date) — stable across re-runs, so re-importing never creates
# duplicate orders for the same medications.csv row.
_MEDICATION_ORDER_NAMESPACE = uuid.UUID("6f5d6a3e-2b3f-4a4d-9c1a-9a2b6b0f9f00")

# ISMP-style high-alert generic drug names — a short, generic clinical list
# (not per-patient), used to flag MedicationOrder.is_high_risk.
_HIGH_RISK_DRUG_NAMES = {"warfarin", "digoxin", "insulin", "heparin", "amiodarone", "lithium", "phenytoin"}

# Extracts a dose token (e.g. "2.5 MG") from a Synthea dispensable-product
# description; everything after it is treated as the route/form ("Oral
# Tablet", "Extended Release Oral Tablet", ...).
_DOSE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:MG|MCG|ML|G|UNT|%|MEQ)", re.IGNORECASE)

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
    # Structured, table-ready data the snapshot fields above can't carry:
    # a real per-observation time series (feeds LabResult) and per-order
    # dose/route/date detail (feeds MedicationOrder). Additive only — the
    # snapshot fields keep their existing shape for backward compatibility.
    lab_series: List[Dict[str, Any]] = field(default_factory=list)
    medication_orders: List[Dict[str, Any]] = field(default_factory=list)


def _clean_name(raw: str) -> str:
    return _NAME_SUFFIX_RE.sub("", raw)


_NON_NAME_TOKENS = {"hr", "er", "xr", "sr", "ml", "mg", "mcg", "unt"}


def _parse_dose_route(description: str) -> tuple[str, str]:
    """Best-effort split of a Synthea dispensable-product description into
    a dose and a route/form string. Some descriptions (e.g. compound
    insulin products) produce a route longer than the `MedicationOrder.route`
    column (String(30)) — truncated to fit, since it's a display fragment,
    not an identifier."""
    match = _DOSE_RE.search(description)
    if not match:
        return "", ""
    return match.group(0)[:60], description[match.end() :].strip()[:30]


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
    lab_series_by_patient: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    observations_path = raw_dir / "observations.csv"
    if observations_path.exists():
        for row in _read_csv(observations_path):
            label = _LAB_CODES.get(row.get("CODE", ""))
            if not label or not row.get("VALUE"):
                continue
            units = row.get("UNITS", "")
            labs_by_patient[row["PATIENT"]][label] = f"{row['VALUE']}{units and ' ' + units}"
            taken_at = row.get("DATE", "")[:10]
            try:
                value = float(row["VALUE"])
            except ValueError:
                continue
            if not taken_at:
                continue
            lab_series_by_patient[row["PATIENT"]].append(
                {"test_name": label, "value": value, "unit": units, "taken_at": taken_at}
            )

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
        medication_orders_by_id: Dict[str, Dict[str, Any]] = {}
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
            dose, route = _parse_dose_route(m["DESCRIPTION"])
            stop = m.get("STOP", "")
            # Same drug/code/start can appear more than once (repeat
            # encounters, refill rows) — dedupe to one order per key,
            # keeping the row with the latest STOP (most complete picture).
            order_id = str(uuid.uuid5(_MEDICATION_ORDER_NAMESPACE, f"{pid}:{m.get('CODE', '')}:{m['START']}"))
            candidate = {
                "id": order_id,
                "name": generic,
                "dose": dose,
                "route": route,
                "start_date": m["START"][:10],
                "end_date": stop[:10] if stop else None,
                "status": "discontinued" if stop else "active",
                "is_high_risk": generic in _HIGH_RISK_DRUG_NAMES,
            }
            existing_order = medication_orders_by_id.get(order_id)
            if existing_order is None or (candidate["end_date"] or "") > (existing_order["end_date"] or ""):
                medication_orders_by_id[order_id] = candidate
        medication_orders = list(medication_orders_by_id.values())
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
                lab_series=lab_series_by_patient.get(pid, []),
                medication_orders=medication_orders,
            )
        )
    return results


async def _insert_into_db(parsed: List[ParsedPatient]) -> None:
    """Manual-use only: inserts alongside the existing demo patients.
    Never called from tests or CI.

    Idempotent, safe to re-run against a DB that already has some/all of
    these patients: `Patient`/`TimelineEvent` are skipped per-patient if
    the id already exists; `LabResult`/`MedicationOrder` are backfilled
    per-patient only if that patient has zero rows in the respective
    table yet, so re-running never duplicates either."""
    from datetime import date as date_cls
    from datetime import datetime as datetime_cls

    from sqlalchemy import func, select  # noqa: PLC0415

    from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
    from data.schemas import LabResult, MedicationOrder, Patient, TimelineEvent  # noqa: PLC0415
    from sephiroth.safety.risk import bp_abnormality, lab_value_abnormality  # noqa: PLC0415

    async with SessionLocal() as session:
        for p in parsed:
            existing = await session.get(Patient, p.id)
            if existing is None:
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

            lab_count = await session.scalar(
                select(func.count()).select_from(LabResult).where(LabResult.patient_id == p.id)
            )
            if lab_count == 0:
                systolic_by_date = {e["taken_at"]: e for e in p.lab_series if e["test_name"] == "bp_systolic"}
                diastolic_by_date = {
                    e["taken_at"]: e for e in p.lab_series if e["test_name"] == "bp_diastolic"
                }
                for entry in p.lab_series:
                    if entry["test_name"] in ("bp_systolic", "bp_diastolic"):
                        pair_date = entry["taken_at"]
                        if pair_date in systolic_by_date and pair_date in diastolic_by_date:
                            is_abnormal, is_critical = bp_abnormality(
                                systolic_by_date[pair_date]["value"], diastolic_by_date[pair_date]["value"]
                            )
                        else:
                            is_abnormal = is_critical = False
                    else:
                        is_abnormal, is_critical = lab_value_abnormality(entry["test_name"], entry["value"])
                    session.add(
                        LabResult(
                            patient_id=p.id,
                            test_name=entry["test_name"],
                            value=entry["value"],
                            unit=entry["unit"],
                            is_abnormal=is_abnormal,
                            is_critical=is_critical,
                            taken_at=datetime_cls.fromisoformat(entry["taken_at"]),
                        )
                    )

            med_count = await session.scalar(
                select(func.count()).select_from(MedicationOrder).where(MedicationOrder.patient_id == p.id)
            )
            if med_count == 0:
                for order in p.medication_orders:
                    session.add(
                        MedicationOrder(
                            id=order["id"],
                            patient_id=p.id,
                            name=order["name"],
                            dose=order["dose"],
                            route=order["route"],
                            start_date=date_cls.fromisoformat(order["start_date"]),
                            end_date=date_cls.fromisoformat(order["end_date"]) if order["end_date"] else None,
                            is_high_risk=order["is_high_risk"],
                            status=order["status"],
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
