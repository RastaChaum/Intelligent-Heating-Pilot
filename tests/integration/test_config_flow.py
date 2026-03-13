"""Integration tests for IntelligentHeatingPilot config flow and options flow."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_AUTO_LEARNING,
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
    CONF_VTHERM_ENTITY,
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

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


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
    default_value = getattr(schema_key, "default", None)
    return default_value() if callable(default_value) else default_value


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_all_values(hass) -> None:
    """Create entry with user-provided values and preserve them in data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == "form"
    assert result["errors"] == {}

    user_input = {
        CONF_NAME: "Living Room IHP",
        CONF_VTHERM_ENTITY: "climate.living_room_vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.schedule_1", "switch.schedule_2"],
        CONF_HUMIDITY_IN_ENTITY: "sensor.living_room_humidity",
        CONF_HUMIDITY_OUT_ENTITY: "sensor.outdoor_humidity",
        CONF_CLOUD_COVER_ENTITY: "sensor.cloud_cover",
        CONF_LHS_RETENTION_DAYS: 40,
        CONF_DEAD_TIME_MINUTES: 10.0,
        CONF_AUTO_LEARNING: False,
        CONF_TEMP_DELTA_THRESHOLD: 0.4,
        CONF_CYCLE_SPLIT_DURATION_MINUTES: 15,
        CONF_MIN_CYCLE_DURATION_MINUTES: 6,
        CONF_MAX_CYCLE_DURATION_MINUTES: 180,
    }

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Living Room IHP"

    data = result2["data"]
    assert data[CONF_NAME] == "Living Room IHP"
    assert data[CONF_VTHERM_ENTITY] == "climate.living_room_vtherm"
    assert data[CONF_SCHEDULER_ENTITIES] == ["switch.schedule_1", "switch.schedule_2"]
    assert data[CONF_HUMIDITY_IN_ENTITY] == "sensor.living_room_humidity"
    assert data[CONF_HUMIDITY_OUT_ENTITY] == "sensor.outdoor_humidity"
    assert data[CONF_CLOUD_COVER_ENTITY] == "sensor.cloud_cover"
    assert data[CONF_LHS_RETENTION_DAYS] == 40
    assert data[CONF_DEAD_TIME_MINUTES] == 10.0
    assert data[CONF_AUTO_LEARNING] is False
    assert data[CONF_TEMP_DELTA_THRESHOLD] == 0.4
    assert data[CONF_CYCLE_SPLIT_DURATION_MINUTES] == 15
    assert data[CONF_MIN_CYCLE_DURATION_MINUTES] == 6
    assert data[CONF_MAX_CYCLE_DURATION_MINUTES] == 180


@pytest.mark.asyncio
async def test_options_flow_persists_and_reopens_with_last_values(hass) -> None:
    """Persist options and re-open the form with the latest values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_config_flow",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_VTHERM_ENTITY: "climate.initial_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.initial_schedule"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    updated_options = {
        CONF_VTHERM_ENTITY: "climate.updated_vtherm",
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
    }

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        updated_options,
    )

    assert result2["type"] == "create_entry"

    for key, value in updated_options.items():
        assert entry.options.get(key) == value

    result3 = await hass.config_entries.options.async_init(entry.entry_id)
    assert result3["type"] == "form"

    schema = result3["data_schema"].schema

    vtherm_key = _find_schema_key(schema, CONF_VTHERM_ENTITY)
    assert _get_default_value(vtherm_key) == "climate.updated_vtherm"

    sched_key = _find_schema_key(schema, CONF_SCHEDULER_ENTITIES)
    assert _get_default_value(sched_key) == ["switch.updated_schedule"]

    hum_in_key = _find_schema_key(schema, CONF_HUMIDITY_IN_ENTITY)
    assert hum_in_key.description.get("suggested_value") == "sensor.updated_humidity_in"

    hum_out_key = _find_schema_key(schema, CONF_HUMIDITY_OUT_ENTITY)
    assert hum_out_key.description.get("suggested_value") == "sensor.updated_humidity_out"

    cloud_key = _find_schema_key(schema, CONF_CLOUD_COVER_ENTITY)
    assert cloud_key.description.get("suggested_value") == "sensor.updated_cloud"

    assert _get_default_value(_find_schema_key(schema, CONF_LHS_RETENTION_DAYS)) == 55
    assert _get_default_value(_find_schema_key(schema, CONF_DEAD_TIME_MINUTES)) == 12.0
    assert _get_default_value(_find_schema_key(schema, CONF_AUTO_LEARNING)) is False
    assert _get_default_value(_find_schema_key(schema, CONF_TEMP_DELTA_THRESHOLD)) == 0.6
    assert _get_default_value(_find_schema_key(schema, CONF_CYCLE_SPLIT_DURATION_MINUTES)) == 25
    assert _get_default_value(_find_schema_key(schema, CONF_MIN_CYCLE_DURATION_MINUTES)) == 8
    assert _get_default_value(_find_schema_key(schema, CONF_MAX_CYCLE_DURATION_MINUTES)) == 200


@pytest.mark.asyncio
async def test_options_flow_values_used_by_device_config_reader(hass) -> None:
    """Use the options flow values as the device config source of truth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_reader",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_VTHERM_ENTITY: "climate.base_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.base_schedule"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    updated_options = {
        CONF_VTHERM_ENTITY: "climate.reader_vtherm",
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
    }

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        updated_options,
    )

    assert result2["type"] == "create_entry"

    reader = HADeviceConfigReader(hass, entry)
    device_config = await reader.get_device_config(entry.entry_id)

    assert device_config.vtherm_entity_id == "climate.reader_vtherm"
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


@pytest.mark.asyncio
async def test_options_flow_defaults_when_no_overrides(hass) -> None:
    """Show defaults when no options are set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_defaults",
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_VTHERM_ENTITY: "climate.default_vtherm",
            CONF_SCHEDULER_ENTITIES: [],
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    schema = result["data_schema"].schema

    vtherm_key = _find_schema_key(schema, CONF_VTHERM_ENTITY)
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
