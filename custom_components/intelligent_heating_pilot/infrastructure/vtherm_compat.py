"""Versatile Thermostat compatibility layer.

This module provides backward-compatible access to VTherm attributes
to support both legacy versions (pre-v8.0.0) and new versions (v8.0.0+).

In v8.0.0+, many attributes were moved under a 'specific_states' nested object.
This module abstracts that change to maintain compatibility.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import State

_LOGGER = logging.getLogger(__name__)


def get_vtherm_attribute(
    state: State | None,
    attribute_name: str,
    default: Any = None,
) -> Any:
    """Get a VTherm attribute with backward compatibility.
    
    Tries to read from the new nested path first (v8.0.0+):
        state.attributes["specific_states"][attribute_name]
    
    Falls back to the legacy root path (pre-v8.0.0):
        state.attributes[attribute_name]
    
    Args:
        state: The VTherm entity state object
        attribute_name: Name of the attribute to retrieve
        default: Default value if attribute not found
        
    Returns:
        The attribute value, or default if not found
        
    Examples:
        >>> # Works with v8.0.0+ (nested structure)
        >>> get_vtherm_attribute(state, "temperature_slope")
        0.04
        
        >>> # Also works with pre-v8.0.0 (flat structure)
        >>> get_vtherm_attribute(state, "temperature_slope")
        0.04
    """
    if not state or not state.attributes:
        return default
    
    # Try new nested path first (v8.0.0+)
    specific_states = state.attributes.get("specific_states")
    if specific_states and isinstance(specific_states, dict):
        value = specific_states.get(attribute_name)
        if value is not None:
            _LOGGER.debug(
                "Found %s in specific_states (v8.0.0+ format): %s",
                attribute_name,
                value,
            )
            return value
    
    # Fallback to legacy root path (pre-v8.0.0)
    value = state.attributes.get(attribute_name)
    if value is not None:
        _LOGGER.debug(
            "Found %s at root level (legacy format): %s",
            attribute_name,
            value,
        )
        return value
    
    _LOGGER.debug(
        "Attribute %s not found in state %s, using default: %s",
        attribute_name,
        state.entity_id,
        default,
    )
    return default
