"""Calendar rules shared by availability reads and booking validation.

Instants and elapsed durations are always handled in UTC. Local wall times
are resolved by roundtrip so gaps disappear and both sides of a fold survive.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from zoneinfo import ZoneInfo

from fastapi import Request

from backend.app.generated.models import Slot, SlotDay


def get_now(request: Request) -> datetime:
    clock = cast(Callable[[], datetime], request.app.state.clock)
    return clock().astimezone(UTC)


def _real_instants(wall: datetime, zone: ZoneInfo) -> list[datetime]:
    instants = set()
    for fold in (0, 1):
        instant = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall:
            instants.add(instant)
    return sorted(instants)


def _fits_workday(start: datetime, end: datetime, day: date, zone: ZoneInfo) -> bool:
    # Check the whole elapsed interval, including transitions that may leave and
    # re-enter working hours on a repeated date. Durations are whole minutes;
    # inspect both sides of each minute for historical sub-minute UTC offsets.
    cursor = start
    while cursor < end:
        segment_end = min(cursor + timedelta(minutes=1), end)
        for point in (cursor, segment_end - timedelta(microseconds=1)):
            local = point.astimezone(zone)
            if local.date() != day or not time(9) <= local.time() < time(18):
                return False
        cursor = segment_end
    return True


def candidate_slots(day: date, duration_minutes: int, now: datetime, zone: ZoneInfo) -> list[Slot]:
    """Return future schedule candidates; occupancy is applied by the caller."""
    if day.weekday() >= 5:
        return []
    slots = []
    for minute in range(9 * 60, 18 * 60, 30):
        wall = datetime.combine(day, time(minute // 60, minute % 60))
        for start in _real_instants(wall, zone):
            end = start + timedelta(minutes=duration_minutes)
            if start > now and _fits_workday(start, end, day, zone):
                slots.append(Slot(startsAt=start, endsAt=end))
    return sorted(slots, key=lambda slot: slot.startsAt)


def schedule_days(duration_minutes: int, now: datetime, zone: ZoneInfo) -> list[SlotDay]:
    today = now.astimezone(zone).date()
    return [
        SlotDay(date=day, slots=candidate_slots(day, duration_minutes, now, zone))
        for day in (today + timedelta(days=offset) for offset in range(14))
    ]
