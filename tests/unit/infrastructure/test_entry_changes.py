"""What a stored entry holds that the running device has not applied yet (#302)."""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.intelligent_heating_pilot.const import (
    CONF_IHP_ENABLED,
    CONF_LHS_RETENTION_DAYS,
    CONF_NAME,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_VTHERM_ENTITY,
    CONF_WAKE_UP_SOURCES,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
    SettingTheme,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.entry_changes import (
    effective_values,
    themes_of,
    unapplied_keys,
)


def _entry(data: dict | None = None, options: dict | None = None) -> Mock:
    entry = Mock()
    entry.data = {CONF_NAME: "Room", CONF_VTHERM_ENTITY: "climate.v", **(data or {})}
    entry.options = options or {}
    return entry


def test_effective_values_let_the_options_override_the_data() -> None:
    entry = _entry(data={CONF_LHS_RETENTION_DAYS: 30}, options={CONF_LHS_RETENTION_DAYS: 60})

    assert effective_values(entry)[CONF_LHS_RETENTION_DAYS] == 60


def test_the_live_toggle_is_not_part_of_the_effective_values() -> None:
    entry = _entry(options={CONF_IHP_ENABLED: False})

    assert CONF_IHP_ENABLED not in effective_values(entry)


def test_nothing_is_unapplied_when_the_entry_matches_the_snapshot() -> None:
    entry = _entry(options={CONF_LHS_RETENTION_DAYS: 60})

    assert unapplied_keys(entry, effective_values(entry)) == set()


def test_a_changed_added_or_removed_key_is_unapplied() -> None:
    snapshot = {CONF_NAME: "Room", CONF_VTHERM_ENTITY: "climate.v", CONF_LHS_RETENTION_DAYS: 30}
    entry = _entry(options={CONF_LHS_RETENTION_DAYS: 60, CONF_TEMPERATURE_OUT_ENTITY: "sensor.o"})
    entry.data = {CONF_VTHERM_ENTITY: "climate.v"}

    assert unapplied_keys(entry, snapshot) == {
        CONF_LHS_RETENTION_DAYS,
        CONF_TEMPERATURE_OUT_ENTITY,
        CONF_NAME,
    }


def test_toggling_the_live_flag_leaves_nothing_unapplied() -> None:
    entry = _entry()
    snapshot = effective_values(entry)
    entry.options = {CONF_IHP_ENABLED: False}

    assert unapplied_keys(entry, snapshot) == set()


def test_there_is_nothing_to_compare_without_a_snapshot() -> None:
    assert unapplied_keys(_entry(options={CONF_LHS_RETENTION_DAYS: 60}), None) == set()


def test_none_and_absent_are_different_values() -> None:
    snapshot = {CONF_VTHERM_ENTITY: "climate.v"}
    entry = _entry(options={CONF_TEMPERATURE_OUT_ENTITY: None})
    entry.data = {CONF_VTHERM_ENTITY: "climate.v"}

    assert unapplied_keys(entry, snapshot) == {CONF_TEMPERATURE_OUT_ENTITY}


def test_keys_map_to_their_themes_in_display_order() -> None:
    themes = themes_of({CONF_WAKE_UP_SOURCES, CONF_LHS_RETENTION_DAYS, CONF_NAME})

    assert themes == [SettingTheme.WAKE_UP_SOURCES, SettingTheme.LEARNING]


def test_a_key_outside_the_catalog_belongs_to_no_theme() -> None:
    assert themes_of({CONF_NAME}) == []
