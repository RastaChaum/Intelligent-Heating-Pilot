"""Helpers of the theme forms: normalizing a submission and not pinning unchanged defaults."""

from __future__ import annotations

from custom_components.intelligent_heating_pilot import const
from custom_components.intelligent_heating_pilot.config_flow_selectors import theme_definitions
from custom_components.intelligent_heating_pilot.config_flow_themes import (
    drop_unchanged_defaults,
    normalize_theme_input,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
    SettingTheme,
)

LEARNING = theme_definitions(SettingTheme.LEARNING)
ENVIRONMENT = theme_definitions(SettingTheme.ENVIRONMENT)
THERMOSTAT = theme_definitions(SettingTheme.THERMOSTAT_SCHEDULERS)


def test_a_cleared_or_missing_optional_entity_is_stored_as_none() -> None:
    values = normalize_theme_input(ENVIRONMENT, {const.CONF_HUMIDITY_OUT_ENTITY: " "})

    assert values[const.CONF_HUMIDITY_OUT_ENTITY] is None
    assert values[const.CONF_TEMPERATURE_OUT_ENTITY] is None


def test_schedulers_are_always_stored_as_a_list() -> None:
    assert normalize_theme_input(THERMOSTAT, {const.CONF_SCHEDULER_ENTITIES: "switch.a"})[
        const.CONF_SCHEDULER_ENTITIES
    ] == ["switch.a"]
    assert normalize_theme_input(THERMOSTAT, {})[const.CONF_SCHEDULER_ENTITIES] == []


def test_a_default_nobody_stored_is_not_pinned() -> None:
    values = {const.CONF_LHS_RETENTION_DAYS: const.DEFAULT_LHS_RETENTION_DAYS}

    assert drop_unchanged_defaults(LEARNING, values, {}) == {}


def test_a_changed_value_is_stored() -> None:
    values = {const.CONF_LHS_RETENTION_DAYS: 60}

    assert drop_unchanged_defaults(LEARNING, values, {}) == values


def test_a_value_already_stored_is_kept_even_when_it_equals_the_default() -> None:
    values = {const.CONF_LHS_RETENTION_DAYS: const.DEFAULT_LHS_RETENTION_DAYS}
    stored = {const.CONF_LHS_RETENTION_DAYS: 90}

    assert drop_unchanged_defaults(LEARNING, values, stored) == values


def test_an_unset_optional_entity_submitted_empty_is_not_pinned_to_none() -> None:
    values = {const.CONF_HUMIDITY_OUT_ENTITY: None}

    assert drop_unchanged_defaults(ENVIRONMENT, values, {}) == {}


def test_an_optional_entity_cleared_after_being_set_is_stored_as_none() -> None:
    values = {const.CONF_HUMIDITY_OUT_ENTITY: None}
    stored = {const.CONF_HUMIDITY_OUT_ENTITY: "sensor.h"}

    assert drop_unchanged_defaults(ENVIRONMENT, values, stored) == values


def test_the_central_entry_is_ignored_when_looking_for_a_vtherm_in_use() -> None:
    from unittest.mock import Mock

    from custom_components.intelligent_heating_pilot.config_flow_themes import vtherm_in_use
    from custom_components.intelligent_heating_pilot.const import (
        CONF_ENTRY_TYPE,
        ENTRY_TYPE_CENTRAL,
    )

    central = Mock(entry_id="central", data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}, options={})
    device = Mock(entry_id="device", data={const.CONF_VTHERM_ENTITY: "climate.a"}, options={})
    hass = Mock()
    hass.config_entries.async_entries.return_value = [central, device]

    assert vtherm_in_use(hass, "climate.a") is True
    assert vtherm_in_use(hass, "climate.b") is False
