"""Pure helpers of the central entry: which devices inherit a changed value (#302)."""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.intelligent_heating_pilot.const import (
    CONF_CLIMATE_ENTITY,
    CONF_ENTRY_TYPE,
    CONF_LHS_RETENTION_DAYS,
    CONF_NAME,
    CONF_TEMPERATURE_OUT_ENTITY,
    ENTRY_TYPE_CENTRAL,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.central_entry import (
    central_values_of,
    changed_central_keys,
    devices_to_reload,
    is_central_entry,
)


def _entry(data: dict | None = None, options: dict | None = None) -> Mock:
    entry = Mock()
    entry.data = data or {}
    entry.options = options or {}
    return entry


def test_an_entry_is_central_by_its_type() -> None:
    assert is_central_entry(_entry({CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}))
    assert not is_central_entry(_entry({CONF_CLIMATE_ENTITY: "climate.v"}))


def test_only_shareable_values_are_read_from_the_central_entry() -> None:
    central = _entry(
        {CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL},
        {CONF_LHS_RETENTION_DAYS: 60, CONF_CLIMATE_ENTITY: "climate.sneaky", CONF_NAME: "x"},
    )

    assert central_values_of(central) == {CONF_LHS_RETENTION_DAYS: 60}


def test_changed_keys_are_the_added_changed_and_removed_ones() -> None:
    central = _entry({}, {CONF_LHS_RETENTION_DAYS: 60, CONF_TEMPERATURE_OUT_ENTITY: "sensor.o"})
    applied = {CONF_LHS_RETENTION_DAYS: 30, "dead_time_minutes": 5}

    assert changed_central_keys(central, applied) == {
        CONF_LHS_RETENTION_DAYS,
        CONF_TEMPERATURE_OUT_ENTITY,
        "dead_time_minutes",
    }


def test_nothing_is_known_to_have_changed_without_an_applied_snapshot() -> None:
    assert changed_central_keys(_entry({}, {CONF_LHS_RETENTION_DAYS: 60}), None) == set()


def test_a_device_that_holds_no_value_for_a_changed_key_is_reloaded() -> None:
    inherits = _entry({CONF_CLIMATE_ENTITY: "climate.a"})

    assert devices_to_reload([inherits], {CONF_LHS_RETENTION_DAYS}) == [inherits]


def test_a_device_overriding_every_changed_key_is_left_alone() -> None:
    overrides = _entry({CONF_CLIMATE_ENTITY: "climate.a"}, {CONF_LHS_RETENTION_DAYS: 90})

    assert devices_to_reload([overrides], {CONF_LHS_RETENTION_DAYS}) == []


def test_a_legacy_value_held_in_data_counts_as_an_override() -> None:
    legacy = _entry({CONF_CLIMATE_ENTITY: "climate.a", CONF_LHS_RETENTION_DAYS: 45})

    assert devices_to_reload([legacy], {CONF_LHS_RETENTION_DAYS}) == []


def test_a_device_overriding_only_some_changed_keys_is_still_reloaded() -> None:
    partial = _entry({}, {CONF_LHS_RETENTION_DAYS: 90})

    assert devices_to_reload([partial], {CONF_LHS_RETENTION_DAYS, "dead_time_minutes"}) == [partial]


def test_an_explicit_none_counts_as_an_override() -> None:
    none = _entry({}, {CONF_TEMPERATURE_OUT_ENTITY: None})

    assert devices_to_reload([none], {CONF_TEMPERATURE_OUT_ENTITY}) == []
