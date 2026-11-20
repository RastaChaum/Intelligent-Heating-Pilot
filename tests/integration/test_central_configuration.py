"""The central configuration entry and the devices that inherit from it (#302)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot import (
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.intelligent_heating_pilot.const import (
    CENTRAL_UNIQUE_ID,
    CONF_ENTRY_TYPE,
    CONF_LHS_RETENTION_DAYS,
    CONF_NAME,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_VTHERM_ENTITY,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_TYPE_CENTRAL,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.central_entry import (
    set_applied_central_values,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)
from tests.integration.options_helpers import save_theme

pytestmark = pytest.mark.usefixtures("flow_environment")

OUTDOOR = "sensor.outdoor"


def _add_central(hass: HomeAssistant, options: dict[str, Any] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="central",
        unique_id=CENTRAL_UNIQUE_ID,
        title="Central configuration",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL},
        options=options or {},
    )
    entry.add_to_hass(hass)
    set_applied_central_values(hass, entry.options)
    return entry


def _add_device(hass: HomeAssistant, entry_id: str, vtherm: str, **extra: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        unique_id=vtherm,
        title=entry_id,
        data={CONF_NAME: DEFAULT_NAME, CONF_VTHERM_ENTITY: vtherm},
        options=extra.get("options", {}),
    )
    entry.add_to_hass(hass)
    return entry


async def _read(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    return await HADeviceConfigReader(hass, entry).get_device_config(entry.entry_id)


# -- creation -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_import_flow_creates_the_central_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
    assert result["result"].unique_id == CENTRAL_UNIQUE_ID


@pytest.mark.asyncio
async def test_a_second_import_aborts(hass: HomeAssistant) -> None:
    _add_central(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
    )

    assert result["type"] is FlowResultType.ABORT


@pytest.mark.asyncio
async def test_a_device_setup_asks_for_the_central_entry_once_it_is_missing(
    hass: HomeAssistant,
) -> None:
    device = _add_device(hass, "living", "climate.living")

    with (
        patch(
            "custom_components.intelligent_heating_pilot.HeatingApplication", autospec=True
        ) as app,
        patch("custom_components.intelligent_heating_pilot.async_at_started"),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch("custom_components.intelligent_heating_pilot.ensure_central_entry") as ensure,
    ):
        app.return_value.async_load = AsyncMock()
        await async_setup_entry(hass, device)

    ensure.assert_called_once_with(hass)


# -- the central entry itself ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_central_entry_loads_without_a_coordinator_or_platform(
    hass: HomeAssistant,
) -> None:
    central = _add_central(hass)

    with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()) as forward:
        assert await async_setup_entry(hass, central) is True
        assert await async_unload_entry(hass, central) is True

    forward.assert_not_called()
    assert central.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_removing_the_central_entry_with_devices_logs_a_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    central = _add_central(hass)
    _add_device(hass, "living", "climate.living")

    with caplog.at_level(logging.WARNING):
        await async_remove_entry(hass, central)

    assert "central configuration was removed" in caplog.text


@pytest.mark.asyncio
async def test_removing_a_device_logs_nothing(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    device = _add_device(hass, "living", "climate.living")

    with caplog.at_level(logging.WARNING):
        await async_remove_entry(hass, device)

    assert "central configuration" not in caplog.text


@pytest.mark.asyncio
async def test_the_central_entry_survives_the_removal_of_every_device(
    hass: HomeAssistant,
) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _add_device(hass, "living", "climate.living")

    await hass.config_entries.async_remove(device.entry_id)

    (remaining,) = hass.config_entries.async_entries(DOMAIN)
    assert remaining.unique_id == CENTRAL_UNIQUE_ID
    assert remaining.options[CONF_LHS_RETENTION_DAYS] == 60


# -- inheritance ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_device_inherits_the_central_value(hass: HomeAssistant) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60, CONF_TEMPERATURE_OUT_ENTITY: OUTDOOR})
    device = _add_device(hass, "living", "climate.living")

    config = await _read(hass, device)

    assert config.lhs_retention_days == 60
    assert config.temperature_out_entity_id == OUTDOOR


@pytest.mark.asyncio
async def test_a_device_override_wins_over_the_central_value(hass: HomeAssistant) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _add_device(hass, "living", "climate.living", options={CONF_LHS_RETENTION_DAYS: 90})

    assert (await _read(hass, device)).lhs_retention_days == 90


@pytest.mark.asyncio
async def test_a_device_can_use_no_sensor_while_the_central_one_is_set(
    hass: HomeAssistant,
) -> None:
    _add_central(hass, {CONF_TEMPERATURE_OUT_ENTITY: OUTDOOR})
    device = _add_device(
        hass, "living", "climate.living", options={CONF_TEMPERATURE_OUT_ENTITY: None}
    )

    assert (await _read(hass, device)).temperature_out_entity_id is None


@pytest.mark.asyncio
async def test_without_a_central_entry_a_device_uses_the_builtin_defaults(
    hass: HomeAssistant,
) -> None:
    device = _add_device(hass, "living", "climate.living")

    config = await _read(hass, device)

    assert config.lhs_retention_days == DEFAULT_LHS_RETENTION_DAYS
    assert config.temperature_out_entity_id is None


@pytest.mark.asyncio
async def test_a_device_created_before_the_feature_keeps_its_values(hass: HomeAssistant) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="legacy",
        unique_id="climate.legacy",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_VTHERM_ENTITY: "climate.legacy",
            CONF_LHS_RETENTION_DAYS: 45,
        },
    )
    entry.add_to_hass(hass)

    assert (await _read(hass, entry)).lhs_retention_days == 45


# -- the central options flow ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_central_menu_lists_only_the_shared_themes(hass: HomeAssistant) -> None:
    central = _add_central(hass)

    menu = await hass.config_entries.options.async_init(central.entry_id)

    assert menu["type"] is FlowResultType.MENU
    assert menu["menu_options"] == [
        "central_native_schedule",
        "central_environment",
        "central_learning",
        "central_cycle_detection",
        "central_anticipation",
    ]


@pytest.mark.asyncio
async def test_a_central_theme_shows_the_shared_fields_directly(hass: HomeAssistant) -> None:
    central = _add_central(hass)
    menu = await hass.config_entries.options.async_init(central.entry_id)

    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_native_schedule"}
    )

    fields = {str(key) for key in form["data_schema"].schema}
    assert "native_schedule_drive" not in fields  # per device, never central
    assert "native_schedule_preset_key" in fields


@pytest.mark.asyncio
async def test_a_central_save_is_stored_without_reloading_a_device(hass: HomeAssistant) -> None:
    central = _add_central(hass)
    _add_device(hass, "living", "climate.living")
    menu = await hass.config_entries.options.async_init(central.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_learning"}
    )

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {CONF_LHS_RETENTION_DAYS: 60}
        )
        await hass.async_block_till_done()

    assert central.options[CONF_LHS_RETENTION_DAYS] == 60
    assert "apply" in result["menu_options"]
    reload.assert_not_called()


@pytest.mark.asyncio
async def test_a_central_value_out_of_range_is_rejected(hass: HomeAssistant) -> None:
    central = _add_central(hass)
    menu = await hass.config_entries.options.async_init(central.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_learning"}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"], {CONF_LHS_RETENTION_DAYS: 1000}
        )

    assert central.options == {}


@pytest.mark.asyncio
async def test_a_cleared_central_sensor_removes_its_key(hass: HomeAssistant) -> None:
    central = _add_central(hass, {CONF_TEMPERATURE_OUT_ENTITY: OUTDOOR})
    menu = await hass.config_entries.options.async_init(central.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_environment"}
    )

    await hass.config_entries.options.async_configure(form["flow_id"], {})

    assert CONF_TEMPERATURE_OUT_ENTITY not in central.options


@pytest.mark.asyncio
async def test_apply_reloads_only_the_devices_that_inherit_the_changed_value(
    hass: HomeAssistant,
) -> None:
    central = _add_central(hass)
    _add_device(hass, "inherits", "climate.a")
    _add_device(hass, "overrides", "climate.b", options={CONF_LHS_RETENTION_DAYS: 90})
    menu = await hass.config_entries.options.async_init(central.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_learning"}
    )
    await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_LHS_RETENTION_DAYS: 60}
    )

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "apply"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    reload.assert_awaited_once_with("inherits")


@pytest.mark.asyncio
async def test_apply_is_not_offered_when_nothing_changed(hass: HomeAssistant) -> None:
    central = _add_central(hass)

    menu = await hass.config_entries.options.async_init(central.entry_id)

    assert "apply" not in menu["menu_options"]


@pytest.mark.asyncio
async def test_a_failing_reload_does_not_stop_the_others(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    central = _add_central(hass)
    _add_device(hass, "first", "climate.a")
    _add_device(hass, "second", "climate.b")
    menu = await hass.config_entries.options.async_init(central.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "central_learning"}
    )
    await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_LHS_RETENTION_DAYS: 60}
    )
    reload = AsyncMock(side_effect=[RuntimeError("boom"), True])

    with patch.object(hass.config_entries, "async_reload", reload):
        await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "apply"}
        )
        await hass.async_block_till_done()

    assert reload.await_count == 2
    assert "Reload after a central change failed" in caplog.text


# -- the device flow with inheritance -------------------------------------------------------


def _loaded_device(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    device = _add_device(hass, "living", "climate.living", **extra)
    device.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[device.entry_id] = Mock(
        _options_snapshot={CONF_NAME: DEFAULT_NAME, CONF_VTHERM_ENTITY: "climate.living"}
    )
    return device


async def _open(hass: HomeAssistant, device: MockConfigEntry, theme: str) -> Any:
    menu = await hass.config_entries.options.async_init(device.entry_id)
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": theme}
    )


@pytest.mark.asyncio
async def test_a_theme_shows_which_settings_are_inherited_and_which_are_overridden(
    hass: HomeAssistant,
) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _loaded_device(hass, options={"dead_time_minutes": 7})

    form = await _open(hass, device, "learning")

    text = form["description_placeholders"]["settings"]
    assert "Slope Data Retention (days): inherited (60)" in text
    assert "Initial Dead Time (minutes): overridden (7)" in text


@pytest.mark.asyncio
async def test_the_picker_is_preselected_with_the_overridden_settings(
    hass: HomeAssistant,
) -> None:
    _add_central(hass)
    device = _loaded_device(hass, options={"dead_time_minutes": 7})

    form = await _open(hass, device, "learning")

    picker = next(k for k in form["data_schema"].schema if str(k) == "overridden_settings")
    assert picker.default() == ["dead_time_minutes"]


@pytest.mark.asyncio
async def test_a_theme_with_only_device_settings_has_no_picker(hass: HomeAssistant) -> None:
    _add_central(hass)
    device = _loaded_device(hass)

    form = await _open(hass, device, "thermostat_schedulers")

    assert "overridden_settings" not in {str(k) for k in form["data_schema"].schema}


@pytest.mark.asyncio
async def test_the_values_form_is_prefilled_with_the_inherited_value(hass: HomeAssistant) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _loaded_device(hass)
    form = await _open(hass, device, "learning")

    values = await hass.config_entries.options.async_configure(
        form["flow_id"], {"overridden_settings": [CONF_LHS_RETENTION_DAYS]}
    )

    marker = next(k for k in values["data_schema"].schema if str(k) == CONF_LHS_RETENTION_DAYS)
    assert marker.default() == 60


@pytest.mark.asyncio
async def test_a_value_equal_to_the_central_one_is_still_an_override(
    hass: HomeAssistant,
) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _loaded_device(hass)
    menu = await hass.config_entries.options.async_init(device.entry_id)

    await save_theme(hass, menu["flow_id"], "learning", {CONF_LHS_RETENTION_DAYS: 60})

    assert device.options[CONF_LHS_RETENTION_DAYS] == 60


@pytest.mark.asyncio
async def test_unselecting_a_setting_resets_it_to_inherit_in_data_and_options(
    hass: HomeAssistant,
) -> None:
    _add_central(hass, {CONF_LHS_RETENTION_DAYS: 60})
    device = _add_device(hass, "living", "climate.living", options={CONF_LHS_RETENTION_DAYS: 90})
    hass.config_entries.async_update_entry(
        device, data={**device.data, CONF_LHS_RETENTION_DAYS: 45}
    )
    device.mock_state(hass, ConfigEntryState.LOADED)
    form = await _open(hass, device, "learning")

    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"overridden_settings": []}
    )

    assert result["type"] is FlowResultType.MENU
    assert CONF_LHS_RETENTION_DAYS not in device.options
    assert CONF_LHS_RETENTION_DAYS not in device.data
    assert (await _read(hass, device)).lhs_retention_days == 60


@pytest.mark.asyncio
async def test_a_reset_without_a_central_value_falls_back_to_the_default(
    hass: HomeAssistant,
) -> None:
    device = _add_device(hass, "living", "climate.living", options={CONF_LHS_RETENTION_DAYS: 90})
    device.mock_state(hass, ConfigEntryState.LOADED)
    form = await _open(hass, device, "learning")

    await hass.config_entries.options.async_configure(form["flow_id"], {"overridden_settings": []})

    assert (await _read(hass, device)).lhs_retention_days == DEFAULT_LHS_RETENTION_DAYS


@pytest.mark.asyncio
async def test_the_native_drive_stays_a_device_setting(hass: HomeAssistant) -> None:
    _add_central(hass)
    device = _loaded_device(hass)

    form = await _open(hass, device, "native_schedule")

    fields = {str(k) for k in form["data_schema"].schema}
    assert "native_schedule_drive" in fields and "overridden_settings" in fields
    picker = next(k for k in form["data_schema"].schema if str(k) == "overridden_settings")
    assert "native_schedule_drive" not in form["data_schema"].schema[picker].config["options"]
