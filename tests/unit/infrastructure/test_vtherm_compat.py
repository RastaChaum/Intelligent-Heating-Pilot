"""Tests for VTherm compatibility layer."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.vtherm_compat import (
    get_vtherm_attribute,
)


def test_get_vtherm_attribute_from_specific_states():
    """Test reading attribute from new v8.0.0+ nested structure."""
    # GIVEN: A VTherm state with v8.0.0+ nested structure
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {
        "specific_states": {
            "temperature_slope": 0.04,
            "ema_temp": 20.25,
            "is_device_active": False,
        }
    }
    
    # WHEN: Reading attributes using the compatibility function
    slope = get_vtherm_attribute(mock_state, "temperature_slope")
    ema_temp = get_vtherm_attribute(mock_state, "ema_temp")
    is_active = get_vtherm_attribute(mock_state, "is_device_active")
    
    # THEN: Should read from nested specific_states
    assert slope == 0.04
    assert ema_temp == 20.25
    assert is_active is False


def test_get_vtherm_attribute_from_root_legacy():
    """Test reading attribute from legacy pre-v8.0.0 flat structure."""
    # GIVEN: A VTherm state with legacy flat structure
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {
        "temperature_slope": 0.05,
        "ema_temp": 21.0,
        "is_device_active": True,
    }
    
    # WHEN: Reading attributes using the compatibility function
    slope = get_vtherm_attribute(mock_state, "temperature_slope")
    ema_temp = get_vtherm_attribute(mock_state, "ema_temp")
    is_active = get_vtherm_attribute(mock_state, "is_device_active")
    
    # THEN: Should read from root level
    assert slope == 0.05
    assert ema_temp == 21.0
    assert is_active is True


def test_get_vtherm_attribute_prefers_specific_states():
    """Test that new nested structure takes precedence over legacy."""
    # GIVEN: A VTherm state with BOTH structures (migration scenario)
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {
        "temperature_slope": 0.05,  # Old value at root
        "specific_states": {
            "temperature_slope": 0.04,  # New value in nested object
        }
    }
    
    # WHEN: Reading the attribute
    slope = get_vtherm_attribute(mock_state, "temperature_slope")
    
    # THEN: Should prefer the new nested value
    assert slope == 0.04


def test_get_vtherm_attribute_missing_returns_default():
    """Test that missing attribute returns default value."""
    # GIVEN: A VTherm state without the requested attribute
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {
        "some_other_attr": "value"
    }
    
    # WHEN: Reading a missing attribute with default
    result = get_vtherm_attribute(mock_state, "missing_attr", default=99.9)
    
    # THEN: Should return the default
    assert result == 99.9


def test_get_vtherm_attribute_none_state():
    """Test that None state returns default."""
    # GIVEN: A None state
    mock_state = None
    
    # WHEN: Reading an attribute
    result = get_vtherm_attribute(mock_state, "temperature_slope", default=0.0)
    
    # THEN: Should return the default
    assert result == 0.0


def test_get_vtherm_attribute_empty_attributes():
    """Test that empty attributes dict returns default."""
    # GIVEN: A state with empty attributes
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {}
    
    # WHEN: Reading an attribute
    result = get_vtherm_attribute(mock_state, "temperature_slope", default=0.0)
    
    # THEN: Should return the default
    assert result == 0.0


def test_get_vtherm_attribute_specific_states_not_dict():
    """Test fallback when specific_states is not a dict."""
    # GIVEN: A state where specific_states is not a dict (malformed)
    mock_state = Mock()
    mock_state.entity_id = "climate.test_vtherm"
    mock_state.attributes = {
        "specific_states": "not a dict",  # Malformed
        "temperature_slope": 0.05,  # Fallback at root
    }
    
    # WHEN: Reading an attribute
    slope = get_vtherm_attribute(mock_state, "temperature_slope")
    
    # THEN: Should fallback to root level
    assert slope == 0.05
