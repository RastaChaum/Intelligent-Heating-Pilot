"""HACS Scheduler, a real Versatile Thermostat and IHP, end to end."""

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
# Half a second past the hour on purpose: HACS Scheduler only accepts a manual run of a slot when
# "now" is strictly after its start, which the live clock's microseconds always satisfy but a
# clock on a round second does not. The test clock then only ever moves by whole seconds.
MONDAY_5AM = "2026-11-16 05:00:00.500000+01:00"
MONDAY_7AM = "2026-11-16 07:00:00+01:00"
ANTICIPATED_START = "sensor.intelligent_heating_pilot_anticipated_start_time"
STARTUP_SETTLE = timedelta(minutes=2)
AFTER_ANTICIPATED_START = timedelta(minutes=1)


@pytest.mark.usefixtures("real_components")
async def test_scheduler_runs_its_own_action_at_the_anticipated_start(
    hass: HomeAssistant, clock: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone(PARIS)
    clock.move_to(MONDAY_5AM)
    await start_cold_room_in_eco(hass)
    scheduler = MockConfigEntry(domain="scheduler", title="Scheduler", data={})
    scheduler.add_to_hass(hass)
    assert await hass.config_entries.async_setup(scheduler.entry_id)
    await hass.services.async_call(
        "scheduler",
        "add",
        {
            "weekdays": ["mon"],
            "repeat_type": "repeat",
            "name": "Heating",
            "timeslots": [
                {
                    "start": "07:00:00",
                    "stop": "09:00:00",
                    "actions": [
                        {
                            "service": "climate.set_preset_mode",
                            "entity_id": THERMOSTAT,
                            "service_data": {"preset_mode": "comfort"},
                        }
                    ],
                }
            ],
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    schedule = next(
        s.entity_id for s in hass.states.async_all("switch") if "schedule" in s.entity_id
    )

    await add_ihp(hass, [schedule])
    await advance(hass, clock, STARTUP_SETTLE)

    anticipated = dt_util.parse_datetime(hass.states.get(ANTICIPATED_START).state)
    assert isinstance(anticipated, datetime)
    assert anticipated < dt_util.parse_datetime(MONDAY_7AM)
    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "eco"

    await advance(hass, clock, anticipated - dt_util.utcnow() + AFTER_ANTICIPATED_START)

    assert hass.states.get(THERMOSTAT).attributes["preset_mode"] == "comfort"
