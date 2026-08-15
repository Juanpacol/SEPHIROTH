"""Tests for the Synthea CSV -> Patient/TimelineEvent parsing logic
(`real_data/patients/import_synthea.py::parse_patients`), against tiny
inline fixture CSVs — never against the real downloaded dataset. Also
verifies the committed `sample_patients.json` artifact is valid and
doesn't collide with the deterministic demo seed (P001/P002)."""

import csv
import datetime
import json
from pathlib import Path

from real_data.patients.import_synthea import (
    RAW_DIR_DEFAULT,
    _compute_age,
    _generic_drug_name,
    parse_patients,
)


def _write_csv(path: Path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_fixture(tmp_path: Path) -> Path:
    _write_csv(
        tmp_path / "patients.csv",
        [
            {
                "Id": "p1",
                "BIRTHDATE": "1970-05-15",
                "DEATHDATE": "",
                "FIRST": "Jane123",
                "LAST": "Doe456",
                "GENDER": "F",
            },
            {
                "Id": "p2",
                "BIRTHDATE": "1990-01-01",
                "DEATHDATE": "",
                "FIRST": "John99",
                "LAST": "Smith1",
                "GENDER": "M",
            },
        ],
        fieldnames=["Id", "BIRTHDATE", "DEATHDATE", "FIRST", "LAST", "GENDER"],
    )
    _write_csv(
        tmp_path / "conditions.csv",
        [
            {"START": "2010-03-01", "PATIENT": "p1", "DESCRIPTION": "Type 2 diabetes"},
            {"START": "2015-06-01", "PATIENT": "p1", "DESCRIPTION": "Hypertension"},
        ],
        fieldnames=["START", "PATIENT", "DESCRIPTION"],
    )
    _write_csv(
        tmp_path / "medications.csv",
        [
            {"START": "2010-03-05", "PATIENT": "p1", "DESCRIPTION": "metFORMIN 500 MG Oral Tablet"},
            {
                "START": "2012-01-01",
                "PATIENT": "p1",
                "DESCRIPTION": "24 HR lisinopril 10 MG Extended Release Oral Tablet",
            },
        ],
        fieldnames=["START", "PATIENT", "DESCRIPTION"],
    )
    _write_csv(
        tmp_path / "allergies.csv",
        [{"PATIENT": "p1", "DESCRIPTION": "Allergy to penicillin"}],
        fieldnames=["PATIENT", "DESCRIPTION"],
    )
    _write_csv(
        tmp_path / "observations.csv",
        [{"PATIENT": "p1", "CODE": "4548-4", "VALUE": "7.1", "UNITS": "%"}],
        fieldnames=["PATIENT", "CODE", "VALUE", "UNITS"],
    )
    return tmp_path


def test_compute_age():
    assert _compute_age("1970-05-15", datetime.date(2026, 5, 14)) == 55
    assert _compute_age("1970-05-15", datetime.date(2026, 5, 15)) == 56


def test_generic_drug_name_strips_dose_and_form():
    assert _generic_drug_name("amLODIPine 2.5 MG Oral Tablet") == "amlodipine"


def test_generic_drug_name_skips_leading_duration_token():
    description = "24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet"
    assert _generic_drug_name(description) == "metformin"


def test_parse_patients_maps_basic_fields(tmp_path):
    fixture_dir = _make_fixture(tmp_path)
    patients = parse_patients(fixture_dir, as_of=datetime.date(2026, 1, 1))
    assert len(patients) == 2

    jane = next(p for p in patients if p.id == "p1")
    assert jane.name == "Jane Doe"
    assert jane.sex == "F"
    assert jane.age == 55
    assert jane.medical_record_number == "SYN-P1"
    assert set(jane.conditions) == {"Type 2 diabetes", "Hypertension"}
    assert set(jane.medications) == {"metformin", "lisinopril"}
    assert jane.allergies == ["Allergy to penicillin"]
    assert jane.lab_results == {"hba1c": "7.1 %"}


def test_parse_patients_builds_sorted_timeline(tmp_path):
    fixture_dir = _make_fixture(tmp_path)
    patients = parse_patients(fixture_dir, as_of=datetime.date(2026, 1, 1))
    jane = next(p for p in patients if p.id == "p1")
    dates = [e["date"] for e in jane.timeline]
    assert dates == sorted(dates)
    types = {e["type"] for e in jane.timeline}
    assert types == {"diagnosis", "medication"}


def test_parse_patients_filters_by_patient_ids(tmp_path):
    fixture_dir = _make_fixture(tmp_path)
    patients = parse_patients(fixture_dir, patient_ids=["p2"], as_of=datetime.date(2026, 1, 1))
    assert len(patients) == 1
    assert patients[0].id == "p2"
    assert patients[0].conditions == []  # no conditions.csv rows for p2


def test_parse_patients_handles_missing_optional_files(tmp_path):
    # allergies.csv / observations.csv are optional in real Synthea exports
    fixture_dir = _make_fixture(tmp_path)
    (fixture_dir / "allergies.csv").unlink()
    (fixture_dir / "observations.csv").unlink()
    patients = parse_patients(fixture_dir, as_of=datetime.date(2026, 1, 1))
    jane = next(p for p in patients if p.id == "p1")
    assert jane.allergies == []
    assert jane.lab_results == {}


def test_committed_sample_patients_json_is_valid():
    path = Path(__file__).parent.parent / "real_data" / "patients" / "sample_patients.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data) > 0
    for patient in data:
        assert {"id", "name", "age", "sex", "medical_record_number", "timeline"} <= patient.keys()
        assert patient["id"] not in ("P001", "P002")  # never collides with the deterministic demo seed


def test_raw_dir_default_points_inside_patients_package():
    assert RAW_DIR_DEFAULT.name == "synthea_raw"
