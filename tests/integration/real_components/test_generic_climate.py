"""IHP preheats a climate that is not a Versatile Thermostat: Home Assistant's own (#252).

The room is heated by the core ``generic_thermostat``, with no Versatile Thermostat set up. It
lists its presets but never publishes their temperatures, so a preset slot is only anticipated
once the user has mapped the preset to a temperature in IHP's options.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.const import (
    CONF_PRESET_TEMPERATURES,
)
from tests.integration.real_components.home import (
    COMFORT_C,
    ECO_C,
    GENERIC_AWAY_C,
    THERMOSTAT,
    Block,
    Home,
)
from tests.integration.real_components.schedulers import (
    ALL_SCHEDULERS,
    ClimateScheduler,
    HacsScheduler,
    NativeSchedule,
)

MORNING = "07:00"
MAPPING = {"away": GENERIC_AWAY_C, "eco": ECO_C, "comfort": COMFORT_C}
DEFAULT_NATIVE_C = 20.0


@pytest.fixture(params=ALL_SCHEDULERS, ids=lambda cls: cls.name)
def scheduler(request: pytest.FixtureRequest):
    return request.param()


async def _preheat_for(home: Home, scheduler, block: Block, **ihp_options):
    entity = await scheduler.install(home, [block])
    await home.start_ihp([entity], **scheduler.ihp_options, **ihp_options)
    await home.settle()
    return entity


@pytest.mark.usefixtures("real_components")
async def test_the_thermostat_is_a_standard_climate_without_versatile_thermostat(
    generic_home: Home, hass: HomeAssistant
) -> None:
    attributes = hass.states.get(THERMOSTAT).attributes

    assert "versatile_thermostat" not in hass.config.components
    assert {"away", "eco", "comfort"} <= set(attributes["preset_modes"])
    assert "preset_temperatures" not in attributes
    assert generic_home.preset == "eco"
    assert generic_home.target == ECO_C


@pytest.mark.usefixtures("real_components")
async def test_ihp_loads_on_the_generic_thermostat(generic_home: Home) -> None:
    entry = await generic_home.start_ihp([])

    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("real_components")
async def test_the_slot_temperature_is_applied_at_the_anticipated_start(
    generic_home: Home, scheduler
) -> None:
    await _preheat_for(generic_home, scheduler, Block(MORNING, temperature=COMFORT_C))

    anticipated = generic_home.anticipated_start
    assert anticipated is not None
    assert generic_home.now < anticipated < generic_home.at(MORNING)
    assert generic_home.target == ECO_C

    await generic_home.reach_anticipated_start()

    assert generic_home.target == COMFORT_C


@pytest.mark.usefixtures("real_components")
async def test_a_mapped_preset_is_applied_at_the_anticipated_start(
    generic_home: Home, scheduler
) -> None:
    await _preheat_for(
        generic_home,
        scheduler,
        Block(MORNING, preset="comfort"),
        **{CONF_PRESET_TEMPERATURES: MAPPING},
    )

    anticipated = generic_home.anticipated_start
    assert anticipated is not None
    assert generic_home.now < anticipated < generic_home.at(MORNING)
    assert generic_home.preset == "eco"

    await generic_home.reach_anticipated_start()

    assert generic_home.preset == "comfort"
    assert generic_home.target == COMFORT_C


@pytest.mark.parametrize(
    "preset_scheduler", [HacsScheduler, ClimateScheduler], ids=lambda cls: cls.name
)
@pytest.mark.usefixtures("real_components")
async def test_an_unmapped_preset_slot_is_not_anticipated_and_says_why(
    generic_home: Home, preset_scheduler, caplog: pytest.LogCaptureFixture
) -> None:
    """Both schedulers publish a preset slot as ``set_preset_mode`` with no temperature."""
    with caplog.at_level(logging.WARNING):
        await _preheat_for(generic_home, preset_scheduler(), Block(MORNING, preset="comfort"))

    assert generic_home.anticipated_start is None
    assert any(
        "comfort" in r.getMessage() and "Map the preset" in r.getMessage() for r in caplog.records
    )

    await generic_home.advance_to(generic_home.at(MORNING) - timedelta(minutes=1))

    assert generic_home.preset == "eco"


@pytest.mark.usefixtures("real_components")
async def test_an_unmapped_native_block_falls_back_to_the_default_temperature(
    generic_home: Home,
) -> None:
    """The comfort block of a native schedule is anticipated for 20 °C, as before #252."""
    await _preheat_for(generic_home, NativeSchedule(), Block(MORNING, preset="comfort"))

    assert generic_home.anticipated_start is not None
    assert generic_home.anticipated_start < generic_home.at(MORNING)


@pytest.mark.usefixtures("real_components")
async def test_the_options_offer_the_presets_of_the_real_thermostat(
    generic_home: Home, hass: HomeAssistant
) -> None:
    entry = await generic_home.start_ihp([])

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert "preset_temperatures" in menu["menu_options"]

    mapping_form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "preset_temperatures"}
    )
    assert mapping_form["step_id"] == "preset_temperatures"
    assert {"away", "eco", "comfort"} <= {str(key) for key in mapping_form["data_schema"].schema}
    assert "none" not in {str(key) for key in mapping_form["data_schema"].schema}

    done = await hass.config_entries.options.async_configure(
        mapping_form["flow_id"], {"comfort": COMFORT_C}
    )
    assert done["type"] == "menu"
    assert entry.options[CONF_PRESET_TEMPERATURES] == {"comfort": COMFORT_C}
