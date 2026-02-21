"""Tests for adapter utilities."""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.intelligent_heating_pilot.infrastructure.adapters.utils import (
    get_entity_name,
)


def test_get_entity_name_returns_friendly_name() -> None:
    """Return friendly name when present."""
    mock_hass = Mock()
    state = Mock()
    state.attributes = {"friendly_name": "Living Room"}
    mock_hass.states.get.return_value = state

    assert get_entity_name(mock_hass, "climate.vtherm") == "Living Room"


def test_get_entity_name_falls_back_to_entity_id_when_missing_state() -> None:
    """Fallback to entity ID when state is missing."""
    mock_hass = Mock()
    mock_hass.states.get.return_value = None

    assert get_entity_name(mock_hass, "climate.vtherm") == "climate.vtherm"


def test_get_entity_name_falls_back_to_entity_id_when_no_friendly_name() -> None:
    """Fallback to entity ID when friendly_name is absent."""
    mock_hass = Mock()
    state = Mock()
    state.attributes = {}
    mock_hass.states.get.return_value = state

    assert get_entity_name(mock_hass, "climate.vtherm") == "climate.vtherm"
