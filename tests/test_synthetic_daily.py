"""The daily synthetic job must read a Synthea BP snapshot as the number it is.

The old digits-only parse turned "131.4 mm[Hg]" into 1314, which then reached
the dashboard as an alert no body could produce (SF068).
"""

import random
from datetime import datetime

import pytest
from sqlalchemy import select

from data.schemas import LabResult, Patient
from sephiroth.clinical.vitals import is_physiologically_plausible
from sephiroth.safety import synthetic_daily


@pytest.fixture
def seen_bp(monkeypatch):
    """Records what `_next_bp` was handed, then lets the real walk run."""
    calls = []
    real = synthetic_daily._next_bp

    def spy(systolic, diastolic):
        calls.append((systolic, diastolic))
        return real(systolic, diastolic)

    monkeypatch.setattr(synthetic_daily, "_next_bp", spy)
    return calls


async def _simulate(db_session, lab_results):
    patient = Patient(
        id="PSD1", name="Synthetic", age=60, sex="F", medical_record_number="PT-PSD1", lab_results=lab_results
    )
    db_session.add(patient)
    await db_session.flush()
    await synthetic_daily._simulate_patient(db_session, patient, datetime(2026, 9, 26, 8, 0))
    await db_session.flush()
    return patient


@pytest.mark.asyncio
async def test_split_bp_with_decimal_and_unit_keeps_its_decimal_point(db_session, seen_bp):
    random.seed(0)
    await _simulate(db_session, {"bp_systolic": "131.4 mm[Hg]", "bp_diastolic": "65.3 mm[Hg]"})

    assert seen_bp == [(131.4, 65.3)]


@pytest.mark.asyncio
async def test_already_corrupted_snapshot_restarts_from_baseline(db_session, seen_bp):
    random.seed(0)
    patient = await _simulate(db_session, {"bp_systolic": "1314", "bp_diastolic": "653"})

    assert seen_bp == [(None, None)]
    rows = (await db_session.scalars(select(LabResult).where(LabResult.patient_id == "PSD1"))).all()
    bp_rows = {r.test_name: r.value for r in rows if r.test_name.startswith("bp_")}
    assert set(bp_rows) == {"bp_systolic", "bp_diastolic"}
    assert all(is_physiologically_plausible(name, value) for name, value in bp_rows.items())
    assert is_physiologically_plausible("bp_systolic", float(patient.lab_results["bp_systolic"]))
