"""Unit tests for the DaylightPeriod value object (#257)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import DaylightPeriod

SUNRISE = datetime(2026, 11, 1, 7, 50, tzinfo=UTC)
SUNSET = datetime(2026, 11, 1, 17, 30, tzinfo=UTC)


def _at(hour: int, minute: int = 0) -> datetime:
    return SUNRISE.replace(hour=hour, minute=minute)


@pytest.fixture
def period() -> DaylightPeriod:
    return DaylightPeriod(sunrise=SUNRISE, sunset=SUNSET)


def test_sunset_before_sunrise_is_rejected() -> None:
    with pytest.raises(ValueError):
        DaylightPeriod(sunrise=SUNSET, sunset=SUNRISE)


def test_sunset_equal_to_sunrise_is_rejected() -> None:
    with pytest.raises(ValueError):
        DaylightPeriod(sunrise=SUNRISE, sunset=SUNRISE)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (_at(6), _at(7), 0.0),  # before sunrise
        (_at(18), _at(19), 0.0),  # after sunset
        (_at(6), _at(7, 50), 0.0),  # ends exactly at sunrise
        (_at(7, 20), _at(8, 20), 30.0),  # straddles sunrise
        (_at(17), _at(18), 30.0),  # straddles sunset
        (_at(10), _at(11, 30), 90.0),  # fully inside
        (_at(6), _at(19), 580.0),  # covers the whole period
    ],
)
def test_overlap_minutes(
    period: DaylightPeriod, start: datetime, end: datetime, expected: float
) -> None:
    assert period.overlap_minutes(start, end) == pytest.approx(expected)


def test_empty_window_has_no_overlap(period: DaylightPeriod) -> None:
    assert period.overlap_minutes(_at(10), _at(10)) == 0.0
