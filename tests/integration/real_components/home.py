"""Build a small real home: a Versatile Thermostat, its sensors and IHP, in the test ``hass``.

Only the physical devices are simulated (room and outdoor sensors, the heater switch). The
thermostat, the schedulers and IHP are the real integrations, so a scenario exercises the
service calls, entity attributes and timers exactly as they behave in a live Home Assistant.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from custom_components.versatile_thermostat.const import (
    CONF_CYCLE_MIN,
    CONF_DEVICE_POWER,
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_NAME,
    CONF_PROP_FUNCTION,
    CONF_STEP_TEMPERATURE,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_SENSOR,
    CONF_THERMOSTAT_SWITCH,
    CONF_THERMOSTAT_TYPE,
    CONF_TPI_COEF_EXT,
    CONF_TPI_COEF_INT,
    CONF_UNDERLYING_LIST,
    CONF_USE_MAIN_CENTRAL_CONFIG,
    PROPORTIONAL_FUNCTION_TPI,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.intelligent_heating_pilot.const import (
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DOMAIN,
)

ROOM_SENSOR = "sensor.room_temperature"
OUTDOOR_SENSOR = "sensor.outdoor_temperature"
HEATER_SWITCH = "switch.heater"
THERMOSTAT = "climate.room"
PRESET_NUMBER = "number.room_preset_{preset}_temp"
THERMOSTAT_MIN_C = 15
THERMOSTAT_MAX_C = 30
THERMOSTAT_STEP_C = 0.5
TPI_COEF_INT = 0.3
TPI_COEF_EXT = 0.1
CYCLE_MINUTES = 5
YIELDS_PER_STEP = 50


async def add_thermostat(hass: HomeAssistant, room_c: float, outdoor_c: float) -> None:
    """Set up a real Versatile Thermostat (over a switch) driven by simulated sensors."""
    hass.states.async_set(ROOM_SENSOR, str(room_c))
    hass.states.async_set(OUTDOOR_SENSOR, str(outdoor_c))
    hass.states.async_set(HEATER_SWITCH, "off")
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    entry = MockConfigEntry(
        domain="versatile_thermostat",
        title="Room",
        data={
            CONF_NAME: "Room",
            CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_SWITCH,
            CONF_TEMP_SENSOR: ROOM_SENSOR,
            CONF_EXTERNAL_TEMP_SENSOR: OUTDOOR_SENSOR,
            CONF_CYCLE_MIN: CYCLE_MINUTES,
            CONF_DEVICE_POWER: 1,
            CONF_USE_MAIN_CENTRAL_CONFIG: False,
            CONF_UNDERLYING_LIST: [HEATER_SWITCH],
            CONF_PROP_FUNCTION: PROPORTIONAL_FUNCTION_TPI,
            CONF_TPI_COEF_INT: TPI_COEF_INT,
            CONF_TPI_COEF_EXT: TPI_COEF_EXT,
            CONF_TEMP_MIN: THERMOSTAT_MIN_C,
            CONF_TEMP_MAX: THERMOSTAT_MAX_C,
            CONF_STEP_TEMPERATURE: THERMOSTAT_STEP_C,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def set_preset_temperatures(hass: HomeAssistant, **celsius_by_preset: float) -> None:
    """Give the thermostat presets their temperature, the way a user does in the UI."""
    for preset, celsius in celsius_by_preset.items():
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": PRESET_NUMBER.format(preset=preset), "value": celsius},
            blocking=True,
        )


async def add_ihp(
    hass: HomeAssistant, scheduler_entities: list[str], options: dict[str, Any] | None = None
) -> MockConfigEntry:
    """Set up IHP on the thermostat, watching the given scheduler entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="IHP",
        data={CONF_VTHERM_ENTITY: THERMOSTAT, CONF_SCHEDULER_ENTITIES: scheduler_entities},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def start_cold_room_in_eco(hass: HomeAssistant, room_c: float = 18.0) -> None:
    """A heating thermostat resting in its eco preset, with a comfort preset to reach."""
    await add_thermostat(hass, room_c=room_c, outdoor_c=5.0)
    await set_preset_temperatures(hass, comfort=21.0, eco=17.0)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": THERMOSTAT, "hvac_mode": "heat"}, blocking=True
    )
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": THERMOSTAT, "preset_mode": "eco"}, blocking=True
    )


async def advance(
    hass: HomeAssistant,
    clock: FrozenDateTimeFactory,
    by: timedelta,
    step: timedelta = timedelta(seconds=3),
) -> None:
    """Move the frozen clock forward in short steps, letting what is due run at each one.

    Components wait with ``asyncio.sleep`` and with timeouts, which only elapse when the clock
    is advanced and the due timers are fired. One big jump would skip the waits that sit
    between two actions (a component that sleeps before acting would never get to act).
    """
    elapsed = timedelta()
    while elapsed < by:
        clock.tick(min(step, by - elapsed))
        elapsed += step
        async_fire_time_changed(hass)
        for _ in range(YIELDS_PER_STEP):
            await asyncio.sleep(0)
