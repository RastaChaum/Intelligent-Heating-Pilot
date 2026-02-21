"""Tests for HAClimateDataReader adapter."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader import (
    HAClimateDataReader,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.states.get = Mock()
    return hass


def _make_state(state_value: str | None = None, attributes: dict | None = None) -> Mock:
    state = Mock()
    state.state = state_value
    state.attributes = attributes or {}
    return state


def test_get_vtherm_entity_id(mock_hass: Mock) -> None:
    """Return the configured VTherm entity ID."""
    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.get_vtherm_entity_id() == "climate.vtherm"


def test_get_current_slope_returns_float(mock_hass: Mock) -> None:
    """Return slope value when available."""
    vtherm_state = _make_state(attributes={"slope": "0.75"})
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.get_current_slope() == 0.75


def test_get_current_slope_returns_none_on_invalid(mock_hass: Mock) -> None:
    """Return None when slope is invalid."""
    vtherm_state = _make_state(attributes={"slope": "bad"})
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.get_current_slope() is None


def test_is_heating_active_true_when_heat_and_below_target(mock_hass: Mock) -> None:
    """Return True when heating is active and below target."""
    vtherm_state = _make_state(
        state_value="heat",
        attributes={"current_temperature": 19.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.is_heating_active() is True


def test_is_heating_active_false_when_not_heating_mode(mock_hass: Mock) -> None:
    """Return False when HVAC mode is not heat."""
    vtherm_state = _make_state(
        state_value="off",
        attributes={"current_temperature": 19.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.is_heating_active() is False


def test_is_heating_active_false_when_at_or_above_target(mock_hass: Mock) -> None:
    """Return False when current temperature is at or above target."""
    vtherm_state = _make_state(
        state_value="heat",
        attributes={"current_temperature": 21.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, "climate.vtherm")

    assert reader.is_heating_active() is False
