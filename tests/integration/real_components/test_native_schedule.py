"""A native Home Assistant schedule, a real Versatile Thermostat and IHP, end to end."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.const import (
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
)
from tests.integration.real_components.home import (
    THERMOSTAT,
    add_ihp,
    advance,
    start_cold_room_in_eco,
)

PARIS = "Europe/Paris"
MONDAY_5AM = "2026-11-16 05:00:00+01:00"
SCHEDULE = "schedule.heating"
ANTICIPATED_START = "sensor.intelligent_heating_pilot_anticipated_start_time"
STARTUP_SETTLE = timedelta(minutes=2)
PAST_DUE = timedelta(hours=2)


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Home Assistant's own schedule helper keeps its next-event timer after the test."""
    return True


@pytest.mark.usefixtures("real_components")
async def test_block_preset_is_applied_to_the_real_thermostat_at_the_anticipated_start(
    hass: HomeAssistant, clock: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone(PARIS)
    clock.move_to(MONDAY_5AM)
    await start_cold_room_in_eco(hass)
    assert await async_setup_component(
        hass,
        "schedule",
        {
            "schedule": {
                "heating": {
                    "name": "Heating",
                    "monday": [
                        {"from": "07:00:00", "to": "09:00:00", "data": {"preset": "comfort"}}
                    ],
                }
            }
        },
    )
    await add_ihp(
        hass,
        [SCHEDULE],
        {CONF_NATIVE_SCHEDULE_DRIVE: True, CONF_NATIVE_SCHEDULE_PRESET_KEY: "preset"},
    )
    await advance(hass, clock, STARTUP_SETTLE)

    anticipated = dt_util.parse_datetime(hass.states.get(ANTICIPATED_START).state)
    assert isinstance(anticipated, datetime)
    assert anticipated < dt_util.parse_datetime("2026-11-16 07:00:00+01:00")
    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "eco"

    await advance(hass, clock, anticipated - dt_util.utcnow() + timedelta(minutes=1))

    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "comfort"
