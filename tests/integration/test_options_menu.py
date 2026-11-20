"""The options of a device: a menu of themes, each saved at once, then "Apply" (#302)."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_CLIMATE_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_NAME,
    CONF_TEMPERATURE_OUT_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.entry_changes import (
    effective_values,
)

pytestmark = pytest.mark.usefixtures("flow_environment")

THEMES = [
    "thermostat_schedulers",
    "native_schedule",
    "wake_up_sources",
    "environment",
    "learning",
    "cycle_detection",
    "anticipation",
]


def _add_device(hass: HomeAssistant, *, loaded: bool = True) -> MockConfigEntry:
    """A device entry; loaded ones have a coordinator holding the snapshot of what it runs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="device",
        unique_id="climate.living",
        title="Living room",
        data={CONF_NAME: DEFAULT_NAME, CONF_CLIMATE_ENTITY: "climate.living"},
        options={CONF_LHS_RETENTION_DAYS: 30},
    )
    entry.add_to_hass(hass)
    if loaded:
        entry.mock_state(hass, ConfigEntryState.LOADED)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = Mock(
            _options_snapshot=effective_values(entry)
        )
    return entry


async def _menu(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return result


async def _save(hass: HomeAssistant, menu: Any, theme: str, values: dict[str, Any]) -> Any:
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": theme}
    )
    assert form["type"] is FlowResultType.FORM
    return await hass.config_entries.options.async_configure(form["flow_id"], values)


@pytest.mark.asyncio
async def test_the_options_open_on_a_menu_of_themes(hass: HomeAssistant) -> None:
    menu = await _menu(hass, _add_device(hass))

    assert menu["menu_options"][: len(THEMES)] == THEMES


@pytest.mark.asyncio
async def test_apply_is_not_offered_when_nothing_is_unapplied(hass: HomeAssistant) -> None:
    menu = await _menu(hass, _add_device(hass))

    assert "apply" not in menu["menu_options"]
    assert menu["description_placeholders"] == {"pending": "-"}


@pytest.mark.asyncio
async def test_apply_is_offered_when_the_device_is_not_loaded(hass: HomeAssistant) -> None:
    menu = await _menu(hass, _add_device(hass, loaded=False))

    assert "apply" in menu["menu_options"]


@pytest.mark.asyncio
async def test_saving_a_theme_stores_at_once_without_reloading(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await _save(hass, menu, "learning", {CONF_LHS_RETENTION_DAYS: 60})

    assert entry.options[CONF_LHS_RETENTION_DAYS] == 60
    assert result["type"] is FlowResultType.MENU
    reload.assert_not_called()


@pytest.mark.asyncio
async def test_after_a_save_apply_is_offered_and_names_the_theme(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)

    result = await _save(hass, menu, "learning", {CONF_LHS_RETENTION_DAYS: 60})

    assert "apply" in result["menu_options"]
    assert result["description_placeholders"]["pending"] != "-"


@pytest.mark.asyncio
async def test_unapplied_changes_survive_closing_and_reopening(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    await _save(hass, await _menu(hass, entry), "learning", {CONF_LHS_RETENTION_DAYS: 60})

    reopened = await _menu(hass, entry)

    assert "apply" in reopened["menu_options"]
    assert entry.options[CONF_LHS_RETENTION_DAYS] == 60


@pytest.mark.asyncio
async def test_two_themes_saved_in_a_row_keep_both(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    await _save(hass, menu, "learning", {CONF_LHS_RETENTION_DAYS: 60})

    await _save(hass, menu, "environment", {CONF_TEMPERATURE_OUT_ENTITY: "sensor.out"})

    assert entry.options[CONF_LHS_RETENTION_DAYS] == 60
    assert entry.options[CONF_TEMPERATURE_OUT_ENTITY] == "sensor.out"


@pytest.mark.asyncio
async def test_apply_reloads_the_device_once_and_closes(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    await _save(hass, menu, "learning", {CONF_LHS_RETENTION_DAYS: 60})

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "apply"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    reload.assert_called_once_with(entry.entry_id)
    assert entry.options[CONF_LHS_RETENTION_DAYS] == 60


@pytest.mark.asyncio
async def test_a_value_out_of_range_is_rejected_and_nothing_is_stored(
    hass: HomeAssistant,
) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "learning"}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"], {CONF_LHS_RETENTION_DAYS: 1000}
        )

    assert entry.options[CONF_LHS_RETENTION_DAYS] == 30


@pytest.mark.asyncio
async def test_a_save_is_merged_onto_the_entry_as_stored_at_that_moment(
    hass: HomeAssistant,
) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "environment"}
    )
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_LHS_RETENTION_DAYS: 75}
    )

    await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_TEMPERATURE_OUT_ENTITY: "sensor.out"}
    )

    assert entry.options[CONF_LHS_RETENTION_DAYS] == 75
    assert entry.options[CONF_TEMPERATURE_OUT_ENTITY] == "sensor.out"


@pytest.mark.asyncio
async def test_a_cleared_optional_entity_is_stored_as_none(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    await _save(hass, menu, "environment", {CONF_HUMIDITY_OUT_ENTITY: "sensor.hum"})

    await _save(hass, menu, "environment", {})

    assert entry.options[CONF_HUMIDITY_OUT_ENTITY] is None


@pytest.mark.asyncio
async def test_the_wake_up_sources_stay_reachable_from_the_menu(hass: HomeAssistant) -> None:
    menu = await _menu(hass, _add_device(hass))

    result = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "wake_up_sources"}
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "wake_up_menu"
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "wake_up_done"}
    )
    assert done["step_id"] == "init"


@pytest.mark.asyncio
async def test_a_theme_without_saving_stores_nothing(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "learning"})

    reopened = await _menu(hass, entry)

    assert entry.options == {CONF_LHS_RETENTION_DAYS: 30}
    assert "apply" not in reopened["menu_options"]


@pytest.mark.asyncio
async def test_submitting_a_theme_unchanged_stores_no_default_and_offers_no_apply(
    hass: HomeAssistant,
) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "learning"}
    )

    # the form is pre-filled with the built-in defaults: submitting them as they are
    result = await hass.config_entries.options.async_configure(form["flow_id"], {})

    assert entry.options == {CONF_LHS_RETENTION_DAYS: 30}
    assert "apply" not in result["menu_options"]


@pytest.mark.asyncio
async def test_a_changed_vtherm_becomes_the_unique_id(hass: HomeAssistant) -> None:
    entry = _add_device(hass)
    menu = await _menu(hass, entry)

    await _save(hass, menu, "thermostat_schedulers", {CONF_CLIMATE_ENTITY: "climate.office"})

    assert entry.unique_id == "climate.office"
    assert entry.options[CONF_CLIMATE_ENTITY] == "climate.office"
