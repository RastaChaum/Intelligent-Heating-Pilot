"""Climate Scheduler, a real Versatile Thermostat and IHP, end to end."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.integration.real_components.home import (
    THERMOSTAT,
    add_ihp,
    advance,
    start_cold_room_in_eco,
)

PARIS = "Europe/Paris"
MONDAY_5AM = "2026-11-16 05:00:00+01:00"
MONDAY_7AM = "2026-11-16 07:00:00+01:00"
GROUP = "Heating"
ANTICIPATED_START = "sensor.intelligent_heating_pilot_anticipated_start_time"
STARTUP_SETTLE = timedelta(minutes=2)
AFTER_ANTICIPATED_START = timedelta(minutes=1)


async def _call(hass: HomeAssistant, service: str, data: dict) -> None:
    await hass.services.async_call("climate_scheduler", service, data, blocking=True)


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Climate Scheduler's own refresh interval keeps running when the test ends."""
    return True


@pytest.mark.usefixtures("real_components")
async def test_node_action_is_applied_to_the_real_thermostat_at_the_anticipated_start(
    hass: HomeAssistant, clock: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone(PARIS)
    clock.move_to(MONDAY_5AM)
    await start_cold_room_in_eco(hass)
    entry = MockConfigEntry(domain="climate_scheduler", title="Climate Scheduler", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _call(hass, "create_group", {"schedule_id": GROUP})
    await _call(hass, "add_to_group", {"schedule_id": GROUP, "entity_id": THERMOSTAT})
    await _call(
        hass,
        "set_group_schedule",
        {
            "schedule_id": GROUP,
            # Climate Scheduler applies the node in force as soon as it knows the group, so the
            # room rests in the night node until the morning one is anticipated.
            "nodes": [
                {"time": "22:00", "temp": 17.0, "preset_mode": "eco"},
                {"time": "07:00", "temp": 21.0, "preset_mode": "comfort"},
            ],
        },
    )
    await advance(hass, clock, timedelta(seconds=6))
    schedule = "switch.schedule_heating"

    await add_ihp(hass, [schedule])
    await advance(hass, clock, STARTUP_SETTLE)

    anticipated = dt_util.parse_datetime(hass.states.get(ANTICIPATED_START).state)
    assert isinstance(anticipated, datetime)
    assert anticipated < dt_util.parse_datetime(MONDAY_7AM)
    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "eco"

    await advance(hass, clock, anticipated - dt_util.utcnow() + AFTER_ANTICIPATED_START)

    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "comfort"
