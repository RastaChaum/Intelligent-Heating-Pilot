"""The selectors built from the catalog keep the bounds of the former forms (#302)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.intelligent_heating_pilot import const
from custom_components.intelligent_heating_pilot.config_flow_selectors import (
    NUMBER_BOUNDS,
    build_theme_schema,
    form_definitions,
    selector_for,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
    SettingTheme,
)

# (minimum, maximum, step, unit) copied from the setup and options forms before #302
GOLDEN_BOUNDS = {
    const.CONF_LHS_RETENTION_DAYS: (7, 90, 1, "days"),
    const.CONF_DEAD_TIME_MINUTES: (0.0, 60.0, 1.0, "minutes"),
    const.CONF_TEMP_DELTA_THRESHOLD: (0.1, 1.0, 0.1, "°C"),
    const.CONF_CYCLE_SPLIT_DURATION_MINUTES: (0, 120, 5, "minutes"),
    const.CONF_MIN_CYCLE_DURATION_MINUTES: (1, 30, 1, "minutes"),
    const.CONF_MAX_CYCLE_DURATION_MINUTES: (15, 360, 5, "minutes"),
    const.CONF_TASK_RANGE_DAYS: (1, 30, 1, "days"),
    const.CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: (1, 60, 1, "minutes"),
    const.CONF_SAFETY_SHUTOFF_GRACE_MINUTES: (0, 30, 1, "minutes"),
}


def _hass() -> Mock:
    hass = Mock()
    hass.states.async_all.return_value = []
    return hass


@pytest.mark.parametrize(("key", "bounds"), GOLDEN_BOUNDS.items())
def test_a_numeric_setting_keeps_its_bounds_and_unit(key: str, bounds: tuple) -> None:
    config = selector_for(key).config

    assert (config["min"], config["max"], config["step"], config["unit_of_measurement"]) == bounds


def test_every_numeric_setting_has_a_golden_bound() -> None:
    assert set(NUMBER_BOUNDS) == set(GOLDEN_BOUNDS)


@pytest.mark.parametrize("key", [const.CONF_AUTO_LEARNING, const.CONF_NATIVE_SCHEDULE_DRIVE])
def test_booleans_use_a_boolean_selector(key: str) -> None:
    assert isinstance(selector_for(key), selector.BooleanSelector)


@pytest.mark.parametrize(
    "key",
    [
        const.CONF_NATIVE_SCHEDULE_PRESET_KEY,
        const.CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
        const.CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    ],
)
def test_the_native_schedule_texts_use_a_text_selector(key: str) -> None:
    assert isinstance(selector_for(key), selector.TextSelector)


def test_every_form_setting_has_a_selector() -> None:
    for definition in form_definitions():
        assert selector_for(definition.key, _hass()) is not None


def test_the_scheduler_selector_needs_hass() -> None:
    with pytest.raises(ValueError):
        selector_for(const.CONF_SCHEDULER_ENTITIES)


def test_a_theme_form_defaults_to_the_builtin_values() -> None:
    from custom_components.intelligent_heating_pilot.config_flow_selectors import theme_definitions

    schema = build_theme_schema(_hass(), theme_definitions(SettingTheme.LEARNING), {})
    defaults = {str(k): k.default() for k in schema.schema if callable(k.default)}

    assert defaults[const.CONF_LHS_RETENTION_DAYS] == const.DEFAULT_LHS_RETENTION_DAYS
    assert defaults[const.CONF_AUTO_LEARNING] is const.DEFAULT_AUTO_LEARNING


def test_a_theme_form_shows_the_current_values() -> None:
    from custom_components.intelligent_heating_pilot.config_flow_selectors import theme_definitions

    schema = build_theme_schema(
        _hass(), theme_definitions(SettingTheme.LEARNING), {const.CONF_LHS_RETENTION_DAYS: 55}
    )
    defaults = {str(k): k.default() for k in schema.schema if callable(k.default)}

    assert defaults[const.CONF_LHS_RETENTION_DAYS] == 55


def test_the_thermostat_is_required_and_the_sensors_suggest_their_value() -> None:
    from custom_components.intelligent_heating_pilot.config_flow_selectors import theme_definitions

    thermostat = build_theme_schema(
        _hass(), theme_definitions(SettingTheme.THERMOSTAT_SCHEDULERS), {}
    )
    environment = build_theme_schema(
        _hass(),
        theme_definitions(SettingTheme.ENVIRONMENT),
        {const.CONF_TEMPERATURE_OUT_ENTITY: "sensor.out"},
    )

    assert any(isinstance(k, vol.Required) for k in thermostat.schema)
    suggested = {
        str(k): k.description.get("suggested_value") for k in environment.schema if k.description
    }
    assert suggested == {const.CONF_TEMPERATURE_OUT_ENTITY: "sensor.out"}


def _state(entity_id: str, **attributes) -> Mock:
    return Mock(entity_id=entity_id, domain=entity_id.split(".")[0], attributes=attributes)


def _hass_with(states: list[Mock], platforms: dict[str, str]) -> Mock:
    hass = _hass()
    hass.states.async_all.return_value = states
    hass.states.get.return_value = None
    registry = Mock()
    registry.async_get = lambda entity_id: (
        Mock(platform=platforms[entity_id]) if entity_id in platforms else None
    )
    return hass, registry


def _offered(states: list[Mock], platforms: dict[str, str]) -> set[str]:
    from unittest.mock import patch

    hass, registry = _hass_with(states, platforms)
    with patch(
        "custom_components.intelligent_heating_pilot.config_flow_selectors.er.async_get",
        return_value=registry,
    ):
        built = selector_for(const.CONF_SCHEDULER_ENTITIES, hass)
    return {option["value"] for option in built.config["options"]}


def test_a_chauffage_sensor_is_offered_as_a_scheduler() -> None:
    states = [
        _state("sensor.living_room_next_change"),
        _state("switch.living_room_schedule"),
    ]

    offered = _offered(states, {"sensor.living_room_next_change": "chauffage"})

    assert offered == {"sensor.living_room_next_change", "switch.living_room_schedule"}


def test_a_plain_sensor_is_not_offered_as_a_scheduler() -> None:
    states = [_state("sensor.phone_next_alarm"), _state("switch.living_room_schedule")]

    offered = _offered(states, {"sensor.phone_next_alarm": "mobile_app"})

    assert offered == {"switch.living_room_schedule"}
