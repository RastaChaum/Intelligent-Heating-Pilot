"""Integration tests for IntelligentHeatingPilot config flow and options flow."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_CLIMATE_ENTITY,
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_MAX_CYCLE_DURATION_MINUTES,
    CONF_MIN_CYCLE_DURATION_MINUTES,
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_TEMP_DELTA_THRESHOLD,
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_TEMP_DELTA_THRESHOLD,
    DOMAIN,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)
from tests.integration.options_helpers import save_theme

pytestmark = pytest.mark.usefixtures("flow_environment")


def _find_schema_key(schema: dict[Any, Any], key_name: str) -> Any:
    for key in schema:
        if getattr(key, "schema", None) == key_name:
            return key
        if getattr(key, "key", None) == key_name:
            return key
        if str(key) == key_name:
            return key
    raise AssertionError(f"Schema key {key_name} not found")


def _get_default_value(schema_key: Any) -> Any:
    """Return the value a field opens with; for an inherit/custom toggle, its custom side."""
    default_value = getattr(schema_key, "default", None)
    value = default_value() if callable(default_value) else default_value
    if isinstance(value, dict) and "active_choice" in value:
        return value.get("custom")
    return value


THEME_KEYS = {
    "thermostat_schedulers": [CONF_CLIMATE_ENTITY, CONF_SCHEDULER_ENTITIES],
    "environment": [
        CONF_HUMIDITY_IN_ENTITY,
        CONF_HUMIDITY_OUT_ENTITY,
        CONF_CLOUD_COVER_ENTITY,
    ],
    "learning": [CONF_LHS_RETENTION_DAYS, CONF_DEAD_TIME_MINUTES, CONF_AUTO_LEARNING],
    "cycle_detection": [
        CONF_TEMP_DELTA_THRESHOLD,
        CONF_CYCLE_SPLIT_DURATION_MINUTES,
        CONF_MIN_CYCLE_DURATION_MINUTES,
        CONF_MAX_CYCLE_DURATION_MINUTES,
    ],
    "anticipation": [CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES],
}


async def _save_in_themes(hass, entry_id: str, values: dict[str, Any]) -> None:
    """Save each value in the theme that holds it, as a user going through the menu does."""
    menu = await hass.config_entries.options.async_init(entry_id)
    assert menu["type"] == "menu"
    for theme, keys in THEME_KEYS.items():
        subset = {key: values[key] for key in keys if key in values}
        result = await save_theme(hass, menu["flow_id"], theme, subset)
        assert result["type"] == "menu"


async def _all_theme_schemas(hass, entry_id: str) -> dict[Any, Any]:
    """The fields of every theme, merged.

    A shareable setting is an inherit/custom toggle whose custom side opens on the effective
    value, stored or inherited.
    """
    schema: dict[Any, Any] = {}
    for theme in THEME_KEYS:
        menu = await hass.config_entries.options.async_init(entry_id)
        form = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": theme}
        )
        schema.update(form["data_schema"].schema)
    return schema


@pytest.mark.asyncio
async def test_user_flow_asks_only_for_the_device_specific_values(hass) -> None:
    """Device creation asks for name, thermostat and schedulers and stores nothing else (#302)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == "form"
    assert result["errors"] == {}
    assert {str(key) for key in result["data_schema"].schema} == {
        CONF_NAME,
        CONF_CLIMATE_ENTITY,
        CONF_SCHEDULER_ENTITIES,
    }

    user_input = {
        CONF_NAME: "Living Room IHP",
        CONF_CLIMATE_ENTITY: "climate.living_room_vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.schedule_1", "switch.schedule_2"],
    }

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Living Room IHP"
    assert result2["data"] == user_input


@pytest.mark.asyncio
async def test_options_flow_persists_and_reopens_with_last_values(hass) -> None:
    """Persist options and re-open the form with the latest values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_config_flow",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_CLIMATE_ENTITY: "climate.initial_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.initial_schedule"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    updated_options = {
        CONF_CLIMATE_ENTITY: "climate.updated_vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.updated_schedule"],
        CONF_HUMIDITY_IN_ENTITY: "sensor.updated_humidity_in",
        CONF_HUMIDITY_OUT_ENTITY: "sensor.updated_humidity_out",
        CONF_CLOUD_COVER_ENTITY: "sensor.updated_cloud",
        CONF_LHS_RETENTION_DAYS: 55,
        CONF_DEAD_TIME_MINUTES: 12.0,
        CONF_AUTO_LEARNING: False,
        CONF_TEMP_DELTA_THRESHOLD: 0.6,
        CONF_CYCLE_SPLIT_DURATION_MINUTES: 25,
        CONF_MIN_CYCLE_DURATION_MINUTES: 8,
        CONF_MAX_CYCLE_DURATION_MINUTES: 200,
        CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: 22,
    }

    await _save_in_themes(hass, entry.entry_id, updated_options)

    for key, value in updated_options.items():
        assert entry.options.get(key) == value

    schema = await _all_theme_schemas(hass, entry.entry_id)

    vtherm_key = _find_schema_key(schema, CONF_CLIMATE_ENTITY)
    assert _get_default_value(vtherm_key) == "climate.updated_vtherm"

    sched_key = _find_schema_key(schema, CONF_SCHEDULER_ENTITIES)
    assert _get_default_value(sched_key) == ["switch.updated_schedule"]

    hum_in_key = _find_schema_key(schema, CONF_HUMIDITY_IN_ENTITY)
    assert hum_in_key.description.get("suggested_value") == "sensor.updated_humidity_in"

    hum_out_key = _find_schema_key(schema, CONF_HUMIDITY_OUT_ENTITY)
    assert _get_default_value(hum_out_key) == "sensor.updated_humidity_out"

    cloud_key = _find_schema_key(schema, CONF_CLOUD_COVER_ENTITY)
    assert _get_default_value(cloud_key) == "sensor.updated_cloud"

    assert _get_default_value(_find_schema_key(schema, CONF_LHS_RETENTION_DAYS)) == 55
    assert _get_default_value(_find_schema_key(schema, CONF_DEAD_TIME_MINUTES)) == 12.0
    assert _get_default_value(_find_schema_key(schema, CONF_AUTO_LEARNING)) is False
    assert _get_default_value(_find_schema_key(schema, CONF_TEMP_DELTA_THRESHOLD)) == 0.6
    assert _get_default_value(_find_schema_key(schema, CONF_CYCLE_SPLIT_DURATION_MINUTES)) == 25
    assert _get_default_value(_find_schema_key(schema, CONF_MIN_CYCLE_DURATION_MINUTES)) == 8
    assert _get_default_value(_find_schema_key(schema, CONF_MAX_CYCLE_DURATION_MINUTES)) == 200
    assert (
        _get_default_value(_find_schema_key(schema, CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES))
        == 22
    )


@pytest.mark.asyncio
async def test_options_flow_values_used_by_device_config_reader(hass) -> None:
    """Use the options flow values as the device config source of truth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_reader",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_CLIMATE_ENTITY: "climate.base_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.base_schedule"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    updated_options = {
        CONF_CLIMATE_ENTITY: "climate.reader_vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.reader_schedule"],
        CONF_HUMIDITY_IN_ENTITY: "sensor.reader_humidity_in",
        CONF_HUMIDITY_OUT_ENTITY: "sensor.reader_humidity_out",
        CONF_CLOUD_COVER_ENTITY: "sensor.reader_cloud",
        CONF_LHS_RETENTION_DAYS: 70,
        CONF_DEAD_TIME_MINUTES: 9.0,
        CONF_AUTO_LEARNING: False,
        CONF_TEMP_DELTA_THRESHOLD: 0.5,
        CONF_CYCLE_SPLIT_DURATION_MINUTES: 20,
        CONF_MIN_CYCLE_DURATION_MINUTES: 7,
        CONF_MAX_CYCLE_DURATION_MINUTES: 240,
        CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: 11,
    }

    await _save_in_themes(hass, entry.entry_id, updated_options)

    reader = HADeviceConfigReader(hass, entry)
    device_config = await reader.get_device_config(entry.entry_id)

    assert device_config.climate_entity_id == "climate.reader_vtherm"
    assert device_config.scheduler_entities == ["switch.reader_schedule"]
    assert device_config.humidity_in_entity_id == "sensor.reader_humidity_in"
    assert device_config.humidity_out_entity_id == "sensor.reader_humidity_out"
    assert device_config.cloud_cover_entity_id == "sensor.reader_cloud"
    assert device_config.lhs_retention_days == 70
    assert device_config.dead_time_minutes == 9.0
    assert device_config.auto_learning is False
    assert device_config.temp_delta_threshold == 0.5
    assert device_config.cycle_split_duration_minutes == 20
    assert device_config.min_cycle_duration_minutes == 7
    assert device_config.max_cycle_duration_minutes == 240
    assert device_config.anticipation_recalc_tolerance_minutes == 11


@pytest.mark.asyncio
async def test_options_flow_defaults_when_no_overrides(hass) -> None:
    """Show defaults when no options are set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_defaults",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_CLIMATE_ENTITY: "climate.default_vtherm",
            CONF_SCHEDULER_ENTITIES: [],
        },
        options={},
    )
    entry.add_to_hass(hass)

    schema = await _all_theme_schemas(hass, entry.entry_id)

    vtherm_key = _find_schema_key(schema, CONF_CLIMATE_ENTITY)
    assert _get_default_value(vtherm_key) == "climate.default_vtherm"

    assert (
        _get_default_value(_find_schema_key(schema, CONF_LHS_RETENTION_DAYS))
        == DEFAULT_LHS_RETENTION_DAYS
    )
    assert (
        _get_default_value(_find_schema_key(schema, CONF_DEAD_TIME_MINUTES))
        == DEFAULT_DEAD_TIME_MINUTES
    )
    assert _get_default_value(_find_schema_key(schema, CONF_AUTO_LEARNING)) == DEFAULT_AUTO_LEARNING
    assert (
        _get_default_value(_find_schema_key(schema, CONF_TEMP_DELTA_THRESHOLD))
        == DEFAULT_TEMP_DELTA_THRESHOLD
    )
    assert (
        _get_default_value(_find_schema_key(schema, CONF_CYCLE_SPLIT_DURATION_MINUTES))
        == DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
    )
    assert (
        _get_default_value(_find_schema_key(schema, CONF_MIN_CYCLE_DURATION_MINUTES))
        == DEFAULT_MIN_CYCLE_DURATION_MINUTES
    )
    assert (
        _get_default_value(_find_schema_key(schema, CONF_MAX_CYCLE_DURATION_MINUTES))
        == DEFAULT_MAX_CYCLE_DURATION_MINUTES
    )
    assert (
        _get_default_value(_find_schema_key(schema, CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES))
        == DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES
    )
