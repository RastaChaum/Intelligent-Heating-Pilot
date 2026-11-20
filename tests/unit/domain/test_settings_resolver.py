"""Resolution of the effective value of a setting: override, then central, then default (#302)."""

from __future__ import annotations

import pytest

from custom_components.intelligent_heating_pilot import const
from custom_components.intelligent_heating_pilot.domain.services.settings_catalog import (
    SettingsCatalog,
)
from custom_components.intelligent_heating_pilot.domain.services.settings_resolver import (
    SettingsResolver,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.resolved_setting import (
    ResolvedSetting,
    SettingSource,
)

RETENTION = const.CONF_LHS_RETENTION_DAYS
OUTDOOR = const.CONF_TEMPERATURE_OUT_ENTITY


@pytest.fixture
def resolve():
    catalog = SettingsCatalog()
    resolver = SettingsResolver()
    return lambda device, central: resolver.resolve(catalog, device, central)


def test_the_default_applies_when_nobody_sets_a_value(resolve) -> None:
    assert resolve({}, {})[RETENTION] == ResolvedSetting(
        RETENTION, const.DEFAULT_LHS_RETENTION_DAYS, SettingSource.DEFAULT
    )


def test_the_central_value_applies_when_the_device_holds_none(resolve) -> None:
    assert resolve({}, {RETENTION: 60})[RETENTION] == ResolvedSetting(
        RETENTION, 60, SettingSource.CENTRAL
    )


def test_the_device_value_wins_over_the_central_one(resolve) -> None:
    assert resolve({RETENTION: 90}, {RETENTION: 60})[RETENTION] == ResolvedSetting(
        RETENTION, 90, SettingSource.OVERRIDE
    )


def test_a_value_equal_to_the_central_one_is_still_an_override(resolve) -> None:
    assert resolve({RETENTION: 60}, {RETENTION: 60})[RETENTION].source is SettingSource.OVERRIDE


def test_none_in_the_device_is_an_override_meaning_none(resolve) -> None:
    resolved = resolve({OUTDOOR: None}, {OUTDOOR: "sensor.outdoor"})[OUTDOOR]

    assert resolved == ResolvedSetting(OUTDOOR, None, SettingSource.OVERRIDE)


def test_an_optional_sensor_with_no_value_anywhere_is_none(resolve) -> None:
    assert resolve({}, {})[OUTDOOR] == ResolvedSetting(OUTDOOR, None, SettingSource.DEFAULT)


def test_a_central_sensor_is_inherited(resolve) -> None:
    assert resolve({}, {OUTDOOR: "sensor.outdoor"})[OUTDOOR].value == "sensor.outdoor"


@pytest.mark.parametrize(
    "key",
    [const.CONF_VTHERM_ENTITY, const.CONF_NATIVE_SCHEDULE_DRIVE, const.CONF_HUMIDITY_IN_ENTITY],
)
def test_a_device_only_setting_never_reads_the_central_values(resolve, key: str) -> None:
    resolved = resolve({}, {key: "from-central"})[key]

    assert resolved.source is SettingSource.DEFAULT
    assert resolved.value != "from-central"


def test_every_catalog_key_is_resolved(resolve) -> None:
    assert set(resolve({}, {})) == {d.key for d in SettingsCatalog().all()}


def test_keys_outside_the_catalog_are_ignored(resolve) -> None:
    assert "name" not in resolve({"name": "Room"}, {})
