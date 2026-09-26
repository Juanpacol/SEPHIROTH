"""SF068 data migration: resolve only the alerts no body could have produced."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

from data.schemas import Alert, Patient

_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations/versions/900b7eb6f507_sf068_resolve_implausible_bp_alerts.py"
)
_spec = importlib.util.spec_from_file_location("sf068_migration", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.mark.parametrize(
    "detail, expected",
    [
        ("BP 1314/653 (≥ 160/100)", True),
        ("BP 171/653 (≥ 160/100)", True),
        ("BP 170/105 (≥ 160/100)", False),
        ("BP 300/200 (≥ 160/100)", False),
        ("", False),
        (None, False),
    ],
)
def test_detail_parsing(detail, expected):
    assert migration.is_implausible_bp_detail(detail) is expected


def _alert(alert_id, detail, *, title="Hypertensive range", source="risk_engine", status="active"):
    return Alert(
        id=alert_id,
        patient_id="PMIG",
        category="lab",
        severity="medium",
        status=status,
        title=title,
        detail=detail,
        source=source,
    )


@pytest.mark.asyncio
async def test_resolves_only_active_risk_engine_alerts_with_impossible_readings(db_session):
    db_session.add(Patient(id="PMIG", name="Nida", age=50, sex="F", medical_record_number="PT-PMIG"))
    db_session.add_all(
        [
            _alert("A-BAD", "BP 1314/653 (≥ 160/100)"),
            _alert("A-REAL", "BP 170/105 (≥ 160/100)"),
            _alert("A-CLINICIAN", "BP 1314/653 (≥ 160/100)", source="clinician"),
            _alert("A-OTHER", "BP 1314/653", title="Something else"),
        ]
    )
    await db_session.commit()

    resolved = await db_session.run_sync(lambda s: migration.resolve_implausible_bp_alerts(s.connection()))
    await db_session.commit()

    assert resolved == 1
    db_session.expire_all()
    alerts = (await db_session.scalars(select(Alert))).all()
    status = {a.id: (a.status, a.resolved_at is not None) for a in alerts}
    assert status == {
        "A-BAD": ("resolved", True),
        "A-REAL": ("active", False),
        "A-CLINICIAN": ("active", False),
        "A-OTHER": ("active", False),
    }
