"""`expand_slots` — pure-function slot computation, no DB, no I/O.

Uses lightweight `SimpleNamespace` stand-ins for the ORM rows
(`AvailabilityRule`/`AvailabilityException`/`Appointment`) since
`expand_slots` only reads attributes — it never touches SQLAlchemy."""

from datetime import date, datetime, time
from types import SimpleNamespace

from api.scheduling import expand_slots


def _rule(
    weekday,
    start_time,
    end_time,
    timezone="UTC",
    slot_minutes=30,
    active=True,
    effective_from=None,
    effective_to=None,
):
    return SimpleNamespace(
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        timezone=timezone,
        slot_minutes=slot_minutes,
        active=active,
        effective_from=effective_from,
        effective_to=effective_to,
    )


def _exception(start_at, end_at, kind):
    return SimpleNamespace(start_at=start_at, end_at=end_at, kind=kind)


def _appointment(start_at, end_at, status="booked"):
    return SimpleNamespace(start_at=start_at, end_at=end_at, status=status)


# 2026-01-05 is a Monday (weekday=0).
MONDAY = date(2026, 1, 5)
TUESDAY = date(2026, 1, 6)


def test_basic_chunking_produces_expected_slot_count():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(11, 0), slot_minutes=30)
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 4
    assert slots[0].start_at == datetime(2026, 1, 5, 9, 0)
    assert slots[0].end_at == datetime(2026, 1, 5, 9, 30)
    assert slots[-1].end_at == datetime(2026, 1, 5, 11, 0)


def test_partial_trailing_slot_is_dropped():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(9, 50), slot_minutes=30)
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 1
    assert slots[0].end_at == datetime(2026, 1, 5, 9, 30)


def test_wrong_weekday_produces_no_slots():
    rule = _rule(weekday=1, start_time=time(9, 0), end_time=time(10, 0))  # Tuesday
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert slots == []


def test_inactive_rule_ignored():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), active=False)
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert slots == []


def test_effective_from_excludes_earlier_dates():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), effective_from=date(2026, 1, 12))
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert slots == []


def test_effective_to_excludes_later_dates():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), effective_to=date(2026, 1, 4))
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert slots == []


def test_effective_window_includes_boundary_dates():
    rule = _rule(
        weekday=0,
        start_time=time(9, 0),
        end_time=time(10, 0),
        effective_from=date(2026, 1, 5),
        effective_to=date(2026, 1, 5),
    )
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 2


def test_block_exception_removes_overlapping_slot_fully():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(11, 0), slot_minutes=30)
    block = _exception(datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 10, 0), kind="block")
    slots = expand_slots([rule], [block], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 2
    assert slots[0].start_at == datetime(2026, 1, 5, 10, 0)


def test_block_exception_removes_partially_overlapping_slot():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), slot_minutes=30)
    block = _exception(datetime(2026, 1, 5, 9, 15), datetime(2026, 1, 5, 9, 20), kind="block")
    slots = expand_slots([rule], [block], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 1
    assert slots[0].start_at == datetime(2026, 1, 5, 9, 30)


def test_block_exception_straddling_two_slots_removes_both():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), slot_minutes=30)
    block = _exception(datetime(2026, 1, 5, 9, 20), datetime(2026, 1, 5, 9, 40), kind="block")
    slots = expand_slots([rule], [block], [], MONDAY, date(2026, 1, 6))
    assert slots == []


def test_open_exception_adds_a_slot_with_no_rule():
    opening = _exception(datetime(2026, 1, 5, 18, 0), datetime(2026, 1, 5, 18, 30), kind="open")
    slots = expand_slots([], [opening], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 1
    assert slots[0].start_at == datetime(2026, 1, 5, 18, 0)


def test_booked_appointment_removes_matching_slot():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), slot_minutes=30)
    appt = _appointment(datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 9, 30))
    slots = expand_slots([rule], [], [appt], MONDAY, date(2026, 1, 6))
    assert len(slots) == 1
    assert slots[0].start_at == datetime(2026, 1, 5, 9, 30)


def test_cancelled_appointment_does_not_block_the_slot():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(9, 30), slot_minutes=30)
    appt = _appointment(datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 9, 30), status="cancelled")
    slots = expand_slots([rule], [], [appt], MONDAY, date(2026, 1, 6))
    assert len(slots) == 1


def test_adjacent_slots_do_not_overlap_each_other():
    """The classic off-by-one: a 09:00-09:30 slot and a 09:30-10:00 slot
    must both survive — they are adjacent, not overlapping."""
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(10, 0), slot_minutes=30)
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 2


def test_empty_rules_and_exceptions_yields_empty_list():
    assert expand_slots([], [], [], MONDAY, date(2026, 1, 6)) == []


def test_multi_week_range_is_sorted_by_start():
    rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(9, 30), slot_minutes=30)
    slots = expand_slots([rule], [], [], MONDAY, date(2026, 1, 20))
    assert len(slots) == 3  # Mondays 1/5, 1/12, 1/19 — 1/20 is the exclusive upper bound
    assert slots[0].start_at < slots[1].start_at < slots[2].start_at
    assert slots[0].start_at == datetime(2026, 1, 5, 9, 0)
    assert slots[1].start_at == datetime(2026, 1, 12, 9, 0)
    assert slots[2].start_at == datetime(2026, 1, 19, 9, 0)


def test_dst_spring_forward_does_not_crash_and_produces_expected_utc_instants():
    """2026-03-08 is the US spring-forward Sunday (02:00 local jumps to
    03:00). Known, documented limitation: `expand_slots` still yields one
    slot per configured `slot_minutes` step (doesn't collapse the missing
    real hour) — asserted here so the behavior stays a documented choice,
    not a silent regression if it ever changes."""
    rule = _rule(
        weekday=6, start_time=time(1, 0), end_time=time(5, 0), timezone="America/New_York", slot_minutes=60
    )
    slots = expand_slots([rule], [], [], date(2026, 3, 8), date(2026, 3, 9))
    assert len(slots) == 4
    assert slots[0].start_at == datetime(2026, 3, 8, 6, 0)  # 01:00 EST == 06:00 UTC


def test_dst_fall_back_does_not_crash_and_produces_expected_utc_instants():
    """2026-11-01 is the US fall-back Sunday (01:00 local occurs twice).
    Same documented limitation as the spring-forward case: one slot per
    configured step, not adjusted for the repeated real hour."""
    rule = _rule(
        weekday=6, start_time=time(1, 0), end_time=time(5, 0), timezone="America/New_York", slot_minutes=60
    )
    slots = expand_slots([rule], [], [], date(2026, 11, 1), date(2026, 11, 2))
    assert len(slots) == 4
    assert slots[0].start_at == datetime(2026, 11, 1, 5, 0)  # 01:00 EDT (fold=0) == 05:00 UTC


def test_multiple_rules_same_day_both_apply():
    morning = _rule(weekday=0, start_time=time(8, 0), end_time=time(9, 0), slot_minutes=30)
    afternoon = _rule(weekday=0, start_time=time(14, 0), end_time=time(15, 0), slot_minutes=30)
    slots = expand_slots([morning, afternoon], [], [], MONDAY, date(2026, 1, 6))
    assert len(slots) == 4


def test_second_weekday_rule_only_applies_on_its_own_day():
    monday_rule = _rule(weekday=0, start_time=time(9, 0), end_time=time(9, 30), slot_minutes=30)
    tuesday_rule = _rule(weekday=1, start_time=time(9, 0), end_time=time(9, 30), slot_minutes=30)
    slots = expand_slots([monday_rule, tuesday_rule], [], [], MONDAY, date(2026, 1, 7))
    assert len(slots) == 2
    assert slots[0].start_at.date() == MONDAY
    assert slots[1].start_at.date() == TUESDAY
