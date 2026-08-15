"""
Download a small, clinically varied sample of Synthea synthetic patients
from the official "Synthea Coherent Data Set" public S3 bucket
(s3://synthea-open-data/coherent/ — CC BY 4.0, see
https://registry.opendata.aws/synthea-coherent-data/), without downloading
the full ~9 GB zip: `patients.csv`/`conditions.csv`/`allergies.csv` are
small enough to fetch whole; `medications.csv` (~90 MB) and
`observations.csv` (~240 MB) are streamed and filtered line-by-line to
only the sample patients' rows, so nothing large ever touches disk.

Run manually (network required, never in CI/tests):

    PYTHONPATH=. python3 real_data/patients/fetch_synthea_sample.py

Writes filtered CSVs to `real_data/patients/synthea_raw/` (gitignored).
Then run `import_synthea.py` to parse and insert them.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Set

import httpx

BASE_URL = "https://synthea-open-data.s3.amazonaws.com/coherent/unzipped/csv"
RAW_DIR = Path(__file__).parent / "synthea_raw"
SAMPLE_SIZE = 25

# Prefer patients whose conditions overlap SEPHIROTH's clinical domain
# (matches the vocabulary already used in data/rag/SEED_GUIDELINES and the
# demo patients in platform/core/db.py) — makes the sample immediately
# useful for demoing the Evidence/Lab/DrugSafety agents.
INTERESTING_KEYWORDS = [
    "diabetes",
    "hypertension",
    "heart failure",
    "chronic kidney",
    "asthma",
    "copd",
    "atrial fibrillation",
    "obesity",
    "hyperlipidemia",
    "depression",
    "anemia",
]


def _get_text(path: str) -> str:
    print(f"Downloading {path}...", file=sys.stderr)
    response = httpx.get(f"{BASE_URL}/{path}", timeout=60)
    response.raise_for_status()
    return response.text


def _select_sample_patient_ids() -> Set[str]:
    patients_text = _get_text("patients.csv")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "patients_full.csv").write_text(patients_text)

    alive_ids = set()
    for row in csv.DictReader(patients_text.splitlines()):
        if not row["DEATHDATE"]:
            alive_ids.add(row["Id"])

    conditions_text = _get_text("conditions.csv")
    conditions_by_patient = defaultdict(list)
    for row in csv.DictReader(conditions_text.splitlines()):
        conditions_by_patient[row["PATIENT"]].append(row["DESCRIPTION"])

    scored = []
    for pid, descriptions in conditions_by_patient.items():
        if pid not in alive_ids:
            continue
        lowered = [d.lower() for d in descriptions]
        hits = sum(1 for d in lowered if any(k in d for k in INTERESTING_KEYWORDS))
        if hits >= 1 and 2 <= len(descriptions) <= 15:
            scored.append((hits, len(descriptions), pid))

    scored.sort(reverse=True)
    sample_ids = {pid for _, _, pid in scored[:SAMPLE_SIZE]}

    # Filter the already-downloaded small files down to the sample.
    _write_filtered_csv(patients_text, RAW_DIR / "patients.csv", id_field="Id", ids=sample_ids)
    _write_filtered_csv(conditions_text, RAW_DIR / "conditions.csv", id_field="PATIENT", ids=sample_ids)
    return sample_ids


def _write_filtered_csv(text: str, out_path: Path, id_field: str, ids: Set[str]) -> None:
    lines = text.splitlines()
    reader = csv.DictReader(lines)
    fieldnames = reader.fieldnames
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        kept = 0
        for row in reader:
            if row[id_field] in ids:
                writer.writerow(row)
                kept += 1
    print(f"{out_path.name}: kept {kept} rows", file=sys.stderr)


def _stream_filter_large_csv(filename: str, out_path: Path, id_field_index: int, ids: Set[str]) -> None:
    """Filter a large CSV (medications/observations) by streaming it line
    by line — never buffers the whole (tens-to-hundreds-of-MB) file."""
    kept = 0
    with httpx.stream("GET", f"{BASE_URL}/{filename}", timeout=180) as response:
        with open(out_path, "w") as out:
            header_written = False
            leftover = ""
            for chunk in response.iter_text():
                leftover += chunk
                lines = leftover.split("\n")
                leftover = lines.pop()  # keep any incomplete trailing line for next chunk
                for line in lines:
                    if not header_written:
                        out.write(line + "\n")
                        header_written = True
                        continue
                    fields = line.split(",")
                    if len(fields) > id_field_index and fields[id_field_index] in ids:
                        out.write(line + "\n")
                        kept += 1
            if leftover.strip():
                fields = leftover.split(",")
                if len(fields) > id_field_index and fields[id_field_index] in ids:
                    out.write(leftover + "\n")
                    kept += 1
    print(f"{out_path.name}: kept {kept} rows (streamed, never fully downloaded)", file=sys.stderr)


def _fetch_small_filtered(filename: str, out_path: Path, id_field: str, ids: Set[str]) -> None:
    text = _get_text(filename)
    _write_filtered_csv(text, out_path, id_field=id_field, ids=ids)


def main() -> int:
    ids = _select_sample_patient_ids()
    print(f"Selected {len(ids)} sample patients.", file=sys.stderr)

    _fetch_small_filtered("allergies.csv", RAW_DIR / "allergies.csv", id_field="PATIENT", ids=ids)
    # medications.csv (~90MB) and observations.csv (~240MB) are too large
    # to fetch whole — stream + filter instead.
    _stream_filter_large_csv("medications.csv", RAW_DIR / "medications.csv", id_field_index=2, ids=ids)
    _stream_filter_large_csv("observations.csv", RAW_DIR / "observations.csv", id_field_index=1, ids=ids)

    (RAW_DIR / "patients_full.csv").unlink(missing_ok=True)  # only needed transiently for selection
    print(f"Done. Filtered CSVs written to {RAW_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
