"""Unit tests for scheduled_slot_of_cycle: which slot a cycle was heating for (#254)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.intelligent_heating_pilot.domain.services.scheduled_slot import (
    scheduled_slot_of_cycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalMeasurement,
)

START = datetime(2026, 11, 1, 6, 20, tzinfo=UTC)
END = datetime(2026, 11, 1, 9, 56, tzinfo=UTC)
TARGET = 20.0
SLOT = datetime(2026, 11, 1, 8, 45, tzinfo=UTC)


def _slot(time: datetime, target: float | str = TARGET) -> HistoricalMeasurement:
    return HistoricalMeasurement(time, target, {}, "sensor.next_schedule_time")


def _slot_of(slots: list[HistoricalMeasurement], start=START, end=END, target=TARGET):
    return scheduled_slot_of_cycle(slots, start, end, target)


def test_slot_that_came_due_during_the_cycle_is_its_slot() -> None:
    assert _slot_of([_slot(SLOT)]) == SLOT


def test_slot_at_the_cycle_end_is_its_slot() -> None:
    assert _slot_of([_slot(END)]) == END


def test_slot_at_the_cycle_start_is_not_its_slot() -> None:
    """The cycle started when the slot was applied: it did not preheat for it."""
    assert _slot_of([_slot(START)]) is None


@pytest.mark.parametrize("offset", [timedelta(minutes=-30), timedelta(minutes=30)])
def test_slot_outside_the_cycle_is_not_its_slot(offset: timedelta) -> None:
    before_or_after = START + offset if offset < timedelta(0) else END + offset
    assert _slot_of([_slot(before_or_after)]) is None


def test_slot_of_another_target_is_not_its_slot() -> None:
    """An 18 °C slot coming due during a 20 °C preheat is not the slot it heated for."""
    assert _slot_of([_slot(SLOT, 18.0)]) is None


def test_slot_target_is_compared_with_float_tolerance() -> None:
    assert _slot_of([_slot(SLOT, 0.1 + 0.2)], target=0.3) == SLOT


def test_first_matching_slot_is_used() -> None:
    later = SLOT + timedelta(minutes=45)
    assert _slot_of([_slot(later), _slot(SLOT)]) == SLOT


def test_slot_without_numeric_target_is_ignored() -> None:
    assert _slot_of([_slot(SLOT, "unknown")]) is None


def test_no_slot_history_gives_no_slot() -> None:
    assert _slot_of([]) is None


def test_naive_cycle_times_are_compared_as_utc() -> None:
    """Cycle times may be naive UTC while the slot history is aware."""
    naive_start = START.replace(tzinfo=None)
    naive_end = END.replace(tzinfo=None)

    assert _slot_of([_slot(SLOT)], start=naive_start, end=naive_end) == SLOT


def test_times_in_other_timezones_are_compared_as_instants() -> None:
    """08:45 UTC is 09:45 in UTC+1: still between 06:20 and 09:56 UTC."""
    local_slot = SLOT.astimezone(timezone(timedelta(hours=1)))

    assert _slot_of([_slot(local_slot)]) == local_slot
