"""Tests for the HASunReader adapter (#257)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

import pytest
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET

from custom_components.intelligent_heating_pilot.domain.value_objects import DaylightPeriod
from custom_components.intelligent_heating_pilot.infrastructure.adapters.sun_reader import (
    HASunReader,
)

ASTRAL_EVENT_DATE = (
    "custom_components.intelligent_heating_pilot.infrastructure.adapters.sun_reader"
    ".get_astral_event_date"
)


def _sun_events(events: dict[tuple[str, date], datetime | None]):
    """Fake get_astral_event_date answering from a (event, date) table."""

    def _event(hass, event: str, day: date) -> datetime | None:
        return events.get((event, day))

    return _event


def _day(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


NOV_1 = date(2026, 11, 1)
NOV_2 = date(2026, 11, 2)
EVENTS = {
    (SUN_EVENT_SUNRISE, NOV_1): _day(1, 6, 50),
    (SUN_EVENT_SUNSET, NOV_1): _day(1, 16, 30),
    (SUN_EVENT_SUNRISE, NOV_2): _day(2, 6, 52),
    (SUN_EVENT_SUNSET, NOV_2): _day(2, 16, 28),
}


@pytest.mark.asyncio
async def test_window_within_one_day_returns_that_day() -> None:
    with patch(ASTRAL_EVENT_DATE, side_effect=_sun_events(EVENTS)):
        periods = await HASunReader(Mock()).get_daylight_periods(_day(1, 3), _day(1, 8))

    assert periods == [DaylightPeriod(_day(1, 6, 50), _day(1, 16, 30))]


@pytest.mark.asyncio
async def test_window_across_midnight_returns_both_days() -> None:
    with patch(ASTRAL_EVENT_DATE, side_effect=_sun_events(EVENTS)):
        periods = await HASunReader(Mock()).get_daylight_periods(_day(1, 22), _day(2, 8))

    assert periods == [
        DaylightPeriod(_day(1, 6, 50), _day(1, 16, 30)),
        DaylightPeriod(_day(2, 6, 52), _day(2, 16, 28)),
    ]


@pytest.mark.asyncio
async def test_day_without_sunrise_or_sunset_has_no_period() -> None:
    """Polar night or polar day: the sun never crosses the horizon that date."""
    events = {**EVENTS, (SUN_EVENT_SUNSET, NOV_1): None}
    with patch(ASTRAL_EVENT_DATE, side_effect=_sun_events(events)):
        periods = await HASunReader(Mock()).get_daylight_periods(_day(1, 3), _day(2, 8))

    assert periods == [DaylightPeriod(_day(2, 6, 52), _day(2, 16, 28))]


@pytest.mark.asyncio
async def test_reads_the_home_location_events() -> None:
    hass = Mock()
    with patch(ASTRAL_EVENT_DATE, side_effect=_sun_events(EVENTS)) as astral:
        await HASunReader(hass).get_daylight_periods(_day(1, 3), _day(1, 8))

    astral.assert_any_call(hass, SUN_EVENT_SUNRISE, NOV_1)
    astral.assert_any_call(hass, SUN_EVENT_SUNSET, NOV_1)
