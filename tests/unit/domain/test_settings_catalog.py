"""The settings catalog declares every configurable setting once (#302)."""

from __future__ import annotations

import pytest

from custom_components.intelligent_heating_pilot import const
from custom_components.intelligent_heating_pilot.domain.services.settings_catalog import (
    SettingsCatalog,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
    SettingDefinition,
    SettingScope,
    SettingTheme,
)

MAX_SETTINGS_PER_THEME = 8
DEVICE_ONLY_KEYS = {
    const.CONF_CLIMATE_ENTITY,
    const.CONF_SCHEDULER_ENTITIES,
    const.CONF_WAKE_UP_SOURCES,
    const.CONF_PRESET_TEMPERATURES,
    const.CONF_HUMIDITY_IN_ENTITY,
    const.CONF_NATIVE_SCHEDULE_DRIVE,
}


@pytest.fixture
def catalog() -> SettingsCatalog:
    return SettingsCatalog()


def test_keys_are_unique(catalog: SettingsCatalog) -> None:
    keys = [definition.key for definition in catalog.all()]
    assert len(keys) == len(set(keys))


def test_device_only_settings_are_not_shareable(catalog: SettingsCatalog) -> None:
    device_only = {d.key for d in catalog.all() if d.scope is SettingScope.DEVICE}
    assert device_only == DEVICE_ONLY_KEYS
    assert not device_only & {d.key for d in catalog.shareable()}


@pytest.mark.parametrize("theme", list(SettingTheme))
def test_no_theme_has_more_than_eight_settings(
    catalog: SettingsCatalog, theme: SettingTheme
) -> None:
    assert len(catalog.of_theme(theme)) <= MAX_SETTINGS_PER_THEME


def test_every_theme_has_a_setting(catalog: SettingsCatalog) -> None:
    for theme in SettingTheme:
        assert catalog.of_theme(theme), theme


def test_shareable_defaults_match_the_constants(catalog: SettingsCatalog) -> None:
    expected = {
        const.CONF_LHS_RETENTION_DAYS: const.DEFAULT_LHS_RETENTION_DAYS,
        const.CONF_DEAD_TIME_MINUTES: const.DEFAULT_DEAD_TIME_MINUTES,
        const.CONF_AUTO_LEARNING: const.DEFAULT_AUTO_LEARNING,
        const.CONF_TASK_RANGE_DAYS: const.DEFAULT_TASK_RANGE_DAYS,
        const.CONF_TEMP_DELTA_THRESHOLD: const.DEFAULT_TEMP_DELTA_THRESHOLD,
        const.CONF_CYCLE_SPLIT_DURATION_MINUTES: const.DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
        const.CONF_MIN_CYCLE_DURATION_MINUTES: const.DEFAULT_MIN_CYCLE_DURATION_MINUTES,
        const.CONF_MAX_CYCLE_DURATION_MINUTES: const.DEFAULT_MAX_CYCLE_DURATION_MINUTES,
        const.CONF_SAFETY_SHUTOFF_GRACE_MINUTES: const.DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
        const.CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: (
            const.DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES
        ),
        const.CONF_NATIVE_SCHEDULE_PRESET_KEY: const.DEFAULT_NATIVE_SCHEDULE_PRESET_KEY,
        const.CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY: const.DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
        const.CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: const.DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
        const.CONF_TEMPERATURE_OUT_ENTITY: None,
        const.CONF_HUMIDITY_OUT_ENTITY: None,
        const.CONF_CLOUD_COVER_ENTITY: None,
    }
    actual = {d.key: d.default for d in catalog.shareable()}
    assert actual == expected


def test_optional_entities_are_the_environment_sensors(catalog: SettingsCatalog) -> None:
    optional = {d.key for d in catalog.all() if d.optional}
    assert optional == {
        const.CONF_HUMIDITY_IN_ENTITY,
        const.CONF_TEMPERATURE_OUT_ENTITY,
        const.CONF_HUMIDITY_OUT_ENTITY,
        const.CONF_CLOUD_COVER_ENTITY,
    }


def test_get_returns_the_definition(catalog: SettingsCatalog) -> None:
    definition = catalog.get(const.CONF_LHS_RETENTION_DAYS)
    assert isinstance(definition, SettingDefinition)
    assert definition.theme is SettingTheme.LEARNING


def test_get_raises_for_an_undeclared_key(catalog: SettingsCatalog) -> None:
    with pytest.raises(KeyError):
        catalog.get("not_a_setting")


def test_a_definition_rejects_an_empty_key() -> None:
    with pytest.raises(ValueError):
        SettingDefinition(
            key="", theme=SettingTheme.LEARNING, scope=SettingScope.SHAREABLE, default=None
        )
