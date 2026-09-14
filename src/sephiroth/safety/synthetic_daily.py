"""Daily synthetic-data pipeline — keeps the demo dashboard's trend views
(`/api/dashboard/evolution`, `/labs`, `/stats`, `/alerts`, `/action-items`)
showing real day-over-day movement instead of a frozen one-time seed.

Every patient in this database is confirmed synthetic (portfolio MVP, not a
real hospital system) — this module nudges each patient's tracked labs
forward by a small random walk each day, occasionally into abnormal/critical
range, and back out again (a plain random walk never reliably returns to
normal on its own, so an already-abnormal value gets a deliberate recovery
chance plus day-over-day pull toward baseline) — then reuses the existing
risk/alert machinery unchanged.

Two write targets, both required: `LabResult` (the real time series read by
`/evolution`/`/labs`) and `Patient.lab_results` (the denormalized snapshot
read by `/stats` and by `generate_alerts_for_patient`) — `Patient.lab_results`
is a plain `EncryptedJSON` column, not `MutableDict`-wrapped, so it must be
*reassigned* as a whole new dict, never mutated in place, or the change is
silently lost on commit.

Idempotent per calendar day via `SyntheticDataRun` (`data.schemas`):
`completed_at` is only set once every step below succeeds, so a row that
exists but never completed means "retry," not "already done" — a plain
`max(LabResult.created_at)` check can't tell those two cases apart if the
process dies mid-run.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import LabResult, Patient, SyntheticDataRun
from sephiroth.safety.alerts import (
    generate_alerts_for_all_patients,
    resolve_recovered_alerts_for_all_patients,
)
from sephiroth.safety.risk import bp_abnormality, lab_value_abnormality
from sephiroth.safety.synthetic_schedule import run_daily_schedule_simulation

logger = logging.getLogger(__name__)

# Only LAB_RULES keys (plus the BP pair) actually influence `/stats` and
# alert generation — generating other test names would be inert for both.
_BASELINE: Dict[str, float] = {
    "potassium": 4.2,
    "inr": 1.1,
    "hba1c": 6.0,
    "bnp": 100.0,
    "ef": 55.0,
    "bmi": 24.0,
    "cholesterol": 180.0,
    "ldl": 100.0,
}
_UNIT: Dict[str, str] = {
    "potassium": "mEq/L",
    "inr": "",
    "hba1c": "%",
    "bnp": "pg/mL",
    "ef": "%",
    "bmi": "",
    "cholesterol": "mg/dL",
    "ldl": "mg/dL",
}
# On the ~10% "jump" days, push straight into a range that reliably crosses
# the corresponding LAB_RULES threshold, rather than trusting a percentage
# nudge to get there from an arbitrary starting value.
_ABNORMAL_JUMP_RANGE: Dict[str, Tuple[float, float]] = {
    "inr": (3.6, 4.5),
    "hba1c": (9.2, 11.0),
    "bnp": (420.0, 650.0),
    "ef": (25.0, 38.0),
    "bmi": (30.5, 42.0),
    "cholesterol": (245.0, 290.0),
    "ldl": (165.0, 210.0),
}
# potassium can go abnormal in either direction (LAB_RULES: <3.5 or >5.5).
_POTASSIUM_JUMP_RANGES: Tuple[Tuple[float, float], Tuple[float, float]] = ((3.0, 3.4), (5.6, 6.2))

_JUMP_PROBABILITY = 0.10
_WALK_PCT = 0.03  # normal-day random walk: +/- 3% of the previous value
# Once a value is already abnormal, an unbiased random walk around ITSELF
# never reliably comes back down -- it wanders, it doesn't revert to mean.
# So an abnormal reading gets its own two-part treatment: a chance of a
# direct recovery (simulating treatment effect), else a pull back toward
# baseline each day so critical patients actually clear over time instead
# of accumulating forever.
_RECOVERY_PROBABILITY = 0.25
_MEAN_REVERSION = 0.25  # fraction of the gap back to baseline closed per day

_BP_BASELINE_SYSTOLIC = 120.0
_BP_BASELINE_DIASTOLIC = 78.0
_BP_JUMP_SYSTOLIC = (165.0, 190.0)
_BP_JUMP_DIASTOLIC = (102.0, 118.0)
_BP_WALK_ABS = 4.0  # normal-day random walk: +/- up to 4 mmHg


@dataclass
class DailySimulationSummary:
    ran: bool
    skipped_already_ran_today: bool = False
    patients_touched: int = 0
    labs_inserted: int = 0
    abnormal_count: int = 0
    critical_count: int = 0
    alerts_created: int = 0
    alerts_resolved: int = 0
    clinicians_touched: int = 0
    availability_rules_seeded: int = 0
    appointments_booked: int = 0
    appointments_completed: int = 0
    appointments_no_show: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ran": self.ran,
            "skipped_already_ran_today": self.skipped_already_ran_today,
            "patients_touched": self.patients_touched,
            "labs_inserted": self.labs_inserted,
            "abnormal_count": self.abnormal_count,
            "critical_count": self.critical_count,
            "alerts_created": self.alerts_created,
            "alerts_resolved": self.alerts_resolved,
            "clinicians_touched": self.clinicians_touched,
            "availability_rules_seeded": self.availability_rules_seeded,
            "appointments_booked": self.appointments_booked,
            "appointments_completed": self.appointments_completed,
            "appointments_no_show": self.appointments_no_show,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


def _next_value(test_name: str, current: Optional[float]) -> float:
    baseline = _BASELINE[test_name]
    was_abnormal = current is not None and lab_value_abnormality(test_name, current)[0]

    if was_abnormal:
        if random.random() < _RECOVERY_PROBABILITY:
            # Direct recovery -- e.g. treatment brought the value back down.
            return round(baseline * (1 + random.uniform(-_WALK_PCT, _WALK_PCT)), 1)
        # Otherwise close part of the gap back to baseline each day, so a
        # critical patient trends toward normal over the following days
        # even without a lucky recovery roll.
        reverted = current + (baseline - current) * _MEAN_REVERSION
        return round(reverted * (1 + random.uniform(-_WALK_PCT, _WALK_PCT)), 1)

    if random.random() < _JUMP_PROBABILITY:
        if test_name == "potassium":
            low, high = random.choice(_POTASSIUM_JUMP_RANGES)
        else:
            low, high = _ABNORMAL_JUMP_RANGE.get(test_name, (baseline, baseline))
        return round(random.uniform(low, high), 1)
    base = current if current is not None else baseline
    return round(base * (1 + random.uniform(-_WALK_PCT, _WALK_PCT)), 1)


def _next_bp(current_systolic: Optional[float], current_diastolic: Optional[float]) -> Tuple[float, float]:
    was_abnormal = (
        current_systolic is not None
        and current_diastolic is not None
        and bp_abnormality(current_systolic, current_diastolic)[0]
    )

    if was_abnormal:
        if random.random() < _RECOVERY_PROBABILITY:
            return (
                round(_BP_BASELINE_SYSTOLIC + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
                round(_BP_BASELINE_DIASTOLIC + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
            )
        systolic = current_systolic + (_BP_BASELINE_SYSTOLIC - current_systolic) * _MEAN_REVERSION
        diastolic = current_diastolic + (_BP_BASELINE_DIASTOLIC - current_diastolic) * _MEAN_REVERSION
        return (
            round(systolic + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
            round(diastolic + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
        )

    if random.random() < _JUMP_PROBABILITY:
        return (
            round(random.uniform(*_BP_JUMP_SYSTOLIC), 0),
            round(random.uniform(*_BP_JUMP_DIASTOLIC), 0),
        )
    systolic = current_systolic if current_systolic is not None else _BP_BASELINE_SYSTOLIC
    diastolic = current_diastolic if current_diastolic is not None else _BP_BASELINE_DIASTOLIC
    return (
        round(systolic + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
        round(diastolic + random.uniform(-_BP_WALK_ABS, _BP_WALK_ABS), 0),
    )


def _format_snapshot_value(test_name: str, value: float, existing_raw: Optional[str]) -> str:
    """Keeps whichever unit-suffix convention the patient's current snapshot
    string already uses (e.g. "6.8%", "102 mg/dL", bare "2.4" for INR);
    falls back to this module's own unit table for a patient with no prior
    value for that test."""
    if existing_raw:
        suffix = "".join(ch for ch in str(existing_raw) if not (ch.isdigit() or ch in ".-"))
        if suffix.strip():
            return f"{value:g}{suffix}"
    unit = _UNIT[test_name]
    return f"{value:g}{unit}" if unit else f"{value:g}"


def _bp_schema(lab_results: dict) -> str:
    by_key_lower = {k.strip().lower() for k in lab_results}
    if "bp_systolic" in by_key_lower and "bp_diastolic" in by_key_lower:
        return "split"
    return "combined"  # matches the seed patients' "bp": "138/86" convention, and is the safe default


async def _simulate_patient(
    session: AsyncSession, patient: Patient, taken_at: datetime
) -> Tuple[int, int, int]:
    """Returns (labs_inserted, abnormal_count, critical_count) for this patient."""
    by_key_lower = {k.strip().lower(): v for k, v in (patient.lab_results or {}).items()}
    new_snapshot = dict(patient.lab_results or {})
    labs_inserted = abnormal_count = critical_count = 0

    for test_name, baseline in _BASELINE.items():
        raw = by_key_lower.get(test_name)
        current = None
        if raw is not None:
            digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch in ".-")
            current = float(digits) if digits else None
        if current is None:
            latest = (
                await session.scalars(
                    select(LabResult)
                    .where(LabResult.patient_id == patient.id, LabResult.test_name == test_name)
                    .order_by(LabResult.taken_at.desc())
                    .limit(1)
                )
            ).first()
            current = latest.value if latest else None

        value = _next_value(test_name, current)
        is_abnormal, is_critical = lab_value_abnormality(test_name, value)
        session.add(
            LabResult(
                patient_id=patient.id,
                test_name=test_name,
                value=value,
                unit=_UNIT[test_name],
                is_abnormal=is_abnormal,
                is_critical=is_critical,
                taken_at=taken_at,
            )
        )
        new_snapshot[test_name] = _format_snapshot_value(test_name, value, raw)
        labs_inserted += 1
        abnormal_count += int(is_abnormal)
        critical_count += int(is_critical)

    schema = _bp_schema(patient.lab_results or {})
    cur_systolic = cur_diastolic = None
    if schema == "split":
        cur_systolic_raw = by_key_lower.get("bp_systolic")
        cur_diastolic_raw = by_key_lower.get("bp_diastolic")
        cur_systolic = (
            float("".join(ch for ch in str(cur_systolic_raw) if ch.isdigit())) if cur_systolic_raw else None
        )
        cur_diastolic = (
            float("".join(ch for ch in str(cur_diastolic_raw) if ch.isdigit())) if cur_diastolic_raw else None
        )
    else:
        combined = by_key_lower.get("bp")
        if combined:
            parts = str(combined).replace(" ", "").split("/")
            if len(parts) == 2:
                try:
                    cur_systolic, cur_diastolic = float(parts[0]), float(parts[1])
                except ValueError:
                    cur_systolic = cur_diastolic = None

    systolic, diastolic = _next_bp(cur_systolic, cur_diastolic)
    bp_abnormal, bp_critical = bp_abnormality(systolic, diastolic)
    for test_name, value in (("bp_systolic", systolic), ("bp_diastolic", diastolic)):
        session.add(
            LabResult(
                patient_id=patient.id,
                test_name=test_name,
                value=value,
                unit="mmHg",
                is_abnormal=bp_abnormal,
                is_critical=bp_critical,
                taken_at=taken_at,
            )
        )
        labs_inserted += 1
        abnormal_count += int(bp_abnormal)
        critical_count += int(bp_critical)

    if schema == "split":
        new_snapshot["bp_systolic"] = f"{systolic:g}"
        new_snapshot["bp_diastolic"] = f"{diastolic:g}"
    else:
        new_snapshot["bp"] = f"{systolic:g}/{diastolic:g}"

    # Whole-dict reassignment -- Patient.lab_results is a plain EncryptedJSON
    # column, not MutableDict-wrapped, so in-place mutation would never flush.
    patient.lab_results = new_snapshot

    return labs_inserted, abnormal_count, critical_count


async def run_daily_simulation(
    session: AsyncSession, *, force: bool = False, dry_run: bool = False
) -> DailySimulationSummary:
    # Naive UTC, matching every other DateTime column in this schema
    # (LabResult.taken_at etc. are all naive) -- an aware datetime here
    # trips asyncpg's "can't subtract offset-naive and offset-aware
    # datetimes" on insert.
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    today = started.date()

    run_row: Optional[SyntheticDataRun] = None
    if not force:
        run_row = (
            await session.scalars(select(SyntheticDataRun).where(SyntheticDataRun.run_date == today))
        ).first()
        if run_row is not None and run_row.completed_at is not None:
            return DailySimulationSummary(ran=False, skipped_already_ran_today=True)

    if run_row is None:
        run_row = SyntheticDataRun(run_date=today)
        session.add(run_row)
        try:
            await session.flush()
        except IntegrityError:
            # Another invocation won the race for today's row (same-day
            # overlapping cron calls) -- treat as "already handled."
            await session.rollback()
            if not force:
                return DailySimulationSummary(ran=False, skipped_already_ran_today=True)
            run_row = (
                await session.scalars(select(SyntheticDataRun).where(SyntheticDataRun.run_date == today))
            ).first()

    summary = DailySimulationSummary(ran=True)
    patients = (await session.scalars(select(Patient))).all()

    for patient in patients:
        try:
            inserted, abnormal, critical = await _simulate_patient(session, patient, started)
        except Exception as exc:  # noqa: BLE001 -- one bad patient must not sink the whole run
            summary.errors.append(f"{patient.id}: {exc}")
            logger.exception("Daily synthetic simulation failed for patient %s", patient.id)
            continue
        summary.patients_touched += 1
        summary.labs_inserted += inserted
        summary.abnormal_count += abnormal
        summary.critical_count += critical

    if dry_run:
        await session.rollback()
        summary.duration_seconds = (datetime.now(timezone.utc).replace(tzinfo=None) - started).total_seconds()
        return summary

    # Labs committed before scheduling runs: book_new_appointments can call
    # session.rollback() internally on an overlap IntegrityError, which
    # would discard any still-uncommitted lab inserts above if scheduling
    # ran first.
    await session.commit()
    summary.alerts_created = await generate_alerts_for_all_patients(session)
    summary.alerts_resolved = await resolve_recovered_alerts_for_all_patients(session)

    try:
        schedule_result = await run_daily_schedule_simulation(session, today=today)
        summary.clinicians_touched = schedule_result["clinicians_touched"]
        summary.availability_rules_seeded = schedule_result["availability_rules_seeded"]
        summary.appointments_booked = schedule_result["appointments_booked"]
        summary.appointments_completed = schedule_result["appointments_completed"]
        summary.appointments_no_show = schedule_result["appointments_no_show"]
        await session.commit()
    except Exception as exc:  # noqa: BLE001 -- scheduling failing must not sink the lab pipeline
        summary.errors.append(f"schedule: {exc}")
        logger.exception("Daily synthetic schedule simulation failed")
        await session.rollback()

    if run_row is not None:
        run_row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run_row.labs_inserted = summary.labs_inserted
        run_row.alerts_created = summary.alerts_created
        run_row.patients_touched = summary.patients_touched
        await session.commit()

    summary.duration_seconds = (datetime.now(timezone.utc).replace(tzinfo=None) - started).total_seconds()
    return summary


__all__ = ["run_daily_simulation", "DailySimulationSummary"]
