"""Tests for HAClimateDataReader.read_climate_snapshot."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from homeassistant.core import State

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader import (
    HAClimateDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

ENTITY = "climate.vtherm"


def _reader(state: State | None) -> HAClimateDataReader:
    hass = Mock()
    hass.states.get = Mock(return_value=state)
    return HAClimateDataReader(hass, RecorderAccessQueue(), ENTITY)


def test_vtherm_requested_state_wins_over_the_visible_values() -> None:
    """Safety or window handling changes the visible preset; the requested one is what counts."""
    state = State(
        ENTITY,
        "heat",
        {
            "preset_mode": "frost",
            "temperature": 7.0,
            "preset_modes": ["eco", "comfort"],
            "specific_states": {
                "requested_state": {
                    "hvac_mode": "heat",
                    "target_temperature": 20.0,
                    "preset": "comfort",
                }
            },
        },
    )

    snapshot = _reader(state).read_climate_snapshot()

    assert snapshot is not None
    assert (snapshot.hvac_mode, snapshot.preset, snapshot.temperature) == ("heat", "comfort", 20.0)
    assert snapshot.available_presets == ("eco", "comfort")


def test_requested_state_is_read_at_the_root_for_older_versions() -> None:
    state = State(
        ENTITY,
        "heat",
        {"requested_state": {"hvac_mode": "off", "target_temperature": 17.0, "preset": "none"}},
    )

    snapshot = _reader(state).read_climate_snapshot()

    assert snapshot is not None and snapshot.hvac_mode == "off"


def test_a_generic_climate_uses_the_standard_attributes() -> None:
    state = State(
        ENTITY,
        "heat",
        {"preset_mode": "eco", "temperature": 18.5, "preset_modes": ["eco", "home"]},
    )

    snapshot = _reader(state).read_climate_snapshot()

    assert snapshot is not None
    assert (snapshot.hvac_mode, snapshot.preset, snapshot.temperature) == ("heat", "eco", 18.5)


def test_a_climate_without_presets_offers_none() -> None:
    snapshot = _reader(State(ENTITY, "heat", {"temperature": 19.0})).read_climate_snapshot()

    assert snapshot is not None
    assert snapshot.preset is None
    assert snapshot.available_presets == ()


@pytest.mark.parametrize("state", [None, State(ENTITY, "unavailable"), State(ENTITY, "unknown")])
def test_an_unavailable_climate_gives_no_snapshot(state) -> None:
    assert _reader(state).read_climate_snapshot() is None


def test_an_unreadable_temperature_gives_an_unknown_target() -> None:
    state = State(ENTITY, "heat", {"preset_mode": "eco", "temperature": "n/a"})

    snapshot = _reader(state).read_climate_snapshot()

    assert snapshot is not None and snapshot.temperature is None
