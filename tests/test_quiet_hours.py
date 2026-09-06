"""Quiet hours — the pure window arithmetic, and the scope precedence.

The wrap-around case (22:00 → 08:00) is the normal one, not the edge case,
which is the whole reason `quiet_window_end` is a function rather than two
comparisons at the call site.

Verifies AC-020-04, AC-020-05 (docs/specs/SPEC-020-automation-correctness.md).
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from api.workflows.memory import set_memory
from api.workflows.quiet_hours import defer_for_quiet_hours
from data.schemas import Patient, User
from sephiroth.workflows.policy import quiet_window_end

BOGOTA = ZoneInfo("America/Bogota")  # UTC-5, no DST


def _utc(hour: int, minute: int = 0, day: int = 6) -> datetime:
    """A naive-UTC instant, the way every datetime in this schema is stored."""
    return datetime(2026, 9, day, hour, minute)


class TestWindowArithmetic:
    def test_a_wrapping_window_covers_late_evening(self):
        # 23:00 in Bogota is 04:00 UTC the next day.
        closes = quiet_window_end(_utc(4, 0, day=7), "22:00", "08:00", BOGOTA)
        assert closes == _utc(13, 0, day=7)  # 08:00 Bogota

    def test_a_wrapping_window_covers_early_morning(self):
        # 02:00 Bogota == 07:00 UTC. Still inside last night's window.
        closes = quiet_window_end(_utc(7, 0, day=7), "22:00", "08:00", BOGOTA)
        assert closes == _utc(13, 0, day=7)

    def test_a_wrapping_window_does_not_cover_the_afternoon(self):
        # 14:00 Bogota == 19:00 UTC.
        assert quiet_window_end(_utc(19, 0), "22:00", "08:00", BOGOTA) is None

    def test_a_same_day_window_behaves_normally(self):
        # 13:30 Bogota == 18:30 UTC, inside 13:00-15:00.
        assert quiet_window_end(_utc(18, 30), "13:00", "15:00", BOGOTA) == _utc(20, 0)
        # 16:00 Bogota == 21:00 UTC, outside it.
        assert quiet_window_end(_utc(21, 0), "13:00", "15:00", BOGOTA) is None

    def test_the_window_is_half_open_at_its_end(self):
        # Exactly 08:00 Bogota is already out of the window; a message sent at
        # the boundary is not "during" quiet hours.
        assert quiet_window_end(_utc(13, 0), "22:00", "08:00", BOGOTA) is None

    def test_a_malformed_window_never_silences_anything(self):
        """The allow-list validates on write, so this only fires on a
        hand-edited row — and 'send it' is the safe failure."""
        for start, end in [("bogus", "08:00"), ("22:00", ""), ("25:99", "08:00")]:
            assert quiet_window_end(_utc(4, 0, day=7), start, end, BOGOTA) is None

    def test_a_zero_length_window_is_not_a_window(self):
        assert quiet_window_end(_utc(4, 0, day=7), "22:00", "22:00", BOGOTA) is None


@pytest.mark.asyncio
class TestScopePrecedence:
    async def _patient(self, session, pid="PQH1"):
        p = Patient(id=pid, name="Quiet Patient", age=44, sex="F", medical_record_number=f"MRN-{pid}")
        session.add(p)
        await session.flush()
        return p

    async def _user(self, session, patient_id=None):
        u = User(
            id=str(uuid4()),
            email=f"{uuid4().hex[:8]}@example.test",
            name="Q",
            hashed_password="x",
            role="patient" if patient_id else "clinician",
            patient_id=patient_id,
        )
        session.add(u)
        await session.flush()
        return u

    async def test_no_window_anywhere_means_send_now(self, db_session):
        patient = await self._patient(db_session)
        assert await defer_for_quiet_hours(db_session, _utc(4, 0, day=7), patient_id=patient.id) is None

    async def test_the_clinic_default_applies_when_nobody_overrides_it(self, db_session, monkeypatch):
        monkeypatch.setattr("core.config.settings.clinic_timezone", "America/Bogota")
        patient = await self._patient(db_session)
        await set_memory(db_session, "clinic", "default", "quiet_hours", {"start": "22:00", "end": "08:00"})
        await db_session.flush()

        assert await defer_for_quiet_hours(db_session, _utc(4, 0, day=7), patient_id=patient.id) is not None

    async def test_a_patients_own_window_beats_the_clinics(self, db_session, monkeypatch):
        """A patient who asked not to be messaged at a particular time has said
        something more specific than the clinic setting, and the more specific
        answer wins — including when it says 'now is fine'."""
        monkeypatch.setattr("core.config.settings.clinic_timezone", "America/Bogota")
        patient = await self._patient(db_session, "PQH2")
        await set_memory(db_session, "clinic", "default", "quiet_hours", {"start": "22:00", "end": "08:00"})
        # This patient only minds the early afternoon.
        await set_memory(db_session, "patient", patient.id, "quiet_hours", {"start": "13:00", "end": "15:00"})
        await db_session.flush()

        # 23:00 Bogota — inside the clinic window, outside the patient's.
        assert await defer_for_quiet_hours(db_session, _utc(4, 0, day=7), patient_id=patient.id) is None
        # 13:30 Bogota — inside the patient's own.
        assert await defer_for_quiet_hours(db_session, _utc(18, 30), patient_id=patient.id) is not None

    async def test_an_unparseable_timezone_falls_back_rather_than_raising(self, db_session, monkeypatch):
        monkeypatch.setattr("core.config.settings.clinic_timezone", "Not/AZone")
        patient = await self._patient(db_session, "PQH3")
        await set_memory(db_session, "clinic", "default", "quiet_hours", {"start": "22:00", "end": "08:00"})
        await db_session.flush()

        # A typo in a setting should make the window wrong, not take the tick
        # down. 04:00 UTC is inside 22:00-08:00 read as UTC.
        assert await defer_for_quiet_hours(db_session, _utc(4, 0, day=7), patient_id=patient.id) is not None
