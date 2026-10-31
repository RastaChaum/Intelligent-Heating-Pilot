"""Unit tests for the contextual hour rule shared by the write and read sides (#214).

A cycle is filed, and a slot is looked up, under the hour nearest to it. A
moment exactly on the half hour belongs to the earlier hour, because cycles end
before their slot rather than after it.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from zoneinfo import ZoneInfo

from custom_components.intelligent_heating_pilot.domain.services.contextual_hour import (
    contextual_hour,
)

DAY = date(2026, 1, 15)
PARIS = ZoneInfo("Europe/Paris")
FALL_BACK_DAY = date(2026, 10, 25)  # 02:00-03:00 occurs twice in Europe/Paris


@pytest.mark.parametrize(
    ("clock", "expected_hour"),
    [
        (time(7, 0), 7),
        (time(6, 58), 7),
        (time(6, 31), 7),
        (time(6, 30), 6),
        (time(6, 30, 0, 1), 7),
        (time(6, 30, 1), 7),
        (time(7, 29, 59), 7),
        (time(7, 30), 7),
        (time(6, 10), 6),
        (time(0, 10), 0),
        (time(23, 30), 23),
        (time(23, 45), 0),
    ],
    ids=[
        "on the hour",
        "just before the hour",
        "just after the half hour",
        "exactly on the half hour",
        "one microsecond past the half hour",
        "one second past the half hour",
        "one second before the next half hour",
        "next half hour",
        "early in the hour",
        "just after midnight",
        "half hour before midnight",
        "after the last half hour wraps to midnight",
    ],
)
def test_contextual_hour_is_the_nearest_hour(clock: time, expected_hour: int) -> None:
    """The nearest hour, the half hour itself going to the earlier hour."""
    assert contextual_hour(datetime.combine(DAY, clock)) == expected_hour


def test_aware_moment_is_read_on_its_own_clock() -> None:
    """A local slot time is rounded on its local clock, not converted to UTC."""
    assert contextual_hour(datetime.combine(DAY, time(6, 58), tzinfo=PARIS)) == 7


@pytest.mark.parametrize("fold", [0, 1])
def test_repeated_hour_at_dst_change_uses_the_wall_clock(fold: int) -> None:
    """Both 02:45 of the autumn change map to 03:00: only the wall clock is read."""
    moment = datetime.combine(FALL_BACK_DAY, time(2, 45, fold=fold), tzinfo=PARIS)

    assert contextual_hour(moment) == 3
