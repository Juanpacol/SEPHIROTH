"""Slot expansion — pure function, no I/O, no DB.

Slots are computed on the fly from a clinician's `AvailabilityRule`s and
`AvailabilityException`s, never materialized: materializing means a slot
table that must be regenerated whenever a rule changes plus a background
job to extend the horizon forever, and a permanent drift class of bugs
where the grid disagrees with the table. Computation over a <=180-day
window with a handful of rules is microseconds and always correct by
construction — and, as a pure function, it's the easiest part of this
feature to unit test exhaustively (DST transitions, exceptions, partial
trailing slots).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

#: Default chunk length for an "open" exception — AvailabilityException
#: carries no slot_minutes of its own (it's a one-off, not a recurring
#: pattern), so an extra opening is chunked at this fixed length.
DEFAULT_OPEN_EXCEPTION_SLOT_MINUTES = 30


@dataclass(frozen=True)
class Slot:
    start_at: datetime  # UTC-naive
    end_at: datetime  # UTC-naive


_UTC = ZoneInfo("UTC")


def _localize_to_utc(naive_wall_clock: datetime, tz: ZoneInfo) -> datetime:
    """Attaches `tz` to a naive wall-clock instant and converts to
    UTC-naive. Each boundary is localized independently from a naive
    value — never by adding a `timedelta` to an already-aware datetime,
    which silently produces wrong results across a DST transition
    (zoneinfo doesn't renormalize on `+`; the offset used at the far end
    would be whatever the *starting* offset happened to be).

    Known limitation, not silently wrong: a wall-clock time that falls
    inside a spring-forward gap (e.g. 02:30 on the day clocks jump from
    02:00 to 03:00) has no real instant — Python/zoneinfo resolves it via
    PEP 495's `fold=0` default (the pre-transition offset) rather than
    raising, so this function always returns exactly one slot per
    configured `slot_minutes` step across the whole window, same as any
    non-transition day. It does not collapse/expand the slot count to
    reflect the "missing"/"repeated" real hour. Getting that right needs
    per-boundary gap/fold detection this MVP doesn't implement — flagged
    as a known limitation (see `docs/dev-log`), not a silent bug."""
    return naive_wall_clock.replace(tzinfo=tz).astimezone(_UTC).replace(tzinfo=None)


def _chunk(local_start: datetime, local_end: datetime, minutes: int, tz: ZoneInfo) -> list[Slot]:
    """Splits `[local_start, local_end)` — both **naive** wall-clock
    datetimes in `tz` — into `minutes`-long chunks, each boundary
    localized independently. Drops any partial trailing slot — a
    09:00-09:50 window at 30-minute slots yields one slot, not
    one-and-a-partial."""
    slots: list[Slot] = []
    cursor = local_start
    step = timedelta(minutes=minutes)
    while cursor + step <= local_end:
        slot_end = cursor + step
        slots.append(Slot(start_at=_localize_to_utc(cursor, tz), end_at=_localize_to_utc(slot_end, tz)))
        cursor = slot_end
    return slots


def _rule_applies(rule, day: date) -> bool:
    if not rule.active or rule.weekday != day.weekday():
        return False
    if rule.effective_from is not None and day < rule.effective_from:
        return False
    if rule.effective_to is not None and day > rule.effective_to:
        return False
    return True


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap: a 09:00-09:30 slot and a 09:30-10:00
    slot do NOT overlap — the single most common off-by-one in
    scheduling code, asserted directly in tests."""
    return a_start < b_end and a_end > b_start


def expand_slots(
    rules: list,
    exceptions: list,
    appointments: list,
    start: date,
    end: date,
) -> list[Slot]:
    """Every open, bookable slot for one clinician in `[start, end)`
    (dates), after subtracting `block` exceptions and existing `booked`
    appointments and adding `open` exceptions. `rules`/`exceptions`/
    `appointments` are the ORM rows already scoped to one clinician by
    the caller — this function does no filtering by clinician_id."""
    candidates: list[Slot] = []

    day = start
    while day < end:
        for rule in rules:
            if not _rule_applies(rule, day):
                continue
            tz = ZoneInfo(rule.timezone)
            local_start = datetime.combine(day, rule.start_time)
            local_end = datetime.combine(day, rule.end_time)
            candidates.extend(_chunk(local_start, local_end, rule.slot_minutes, tz))
        day += timedelta(days=1)

    for exc in exceptions:
        if exc.kind != "open":
            continue
        candidates.extend(
            _chunk(
                exc.start_at,
                exc.end_at,
                DEFAULT_OPEN_EXCEPTION_SLOT_MINUTES,
                _UTC,
            )
        )

    blocks = [(e.start_at, e.end_at) for e in exceptions if e.kind == "block"]
    booked = [(a.start_at, a.end_at) for a in appointments if a.status == "booked"]

    open_slots = []
    seen = set()
    for slot in candidates:
        key = (slot.start_at, slot.end_at)
        if key in seen:
            continue
        if any(_overlaps(slot.start_at, slot.end_at, bs, be) for bs, be in blocks):
            continue
        if any(_overlaps(slot.start_at, slot.end_at, bs, be) for bs, be in booked):
            continue
        seen.add(key)
        open_slots.append(slot)

    return sorted(open_slots, key=lambda s: s.start_at)


__all__ = ["Slot", "expand_slots", "DEFAULT_OPEN_EXCEPTION_SLOT_MINUTES"]
