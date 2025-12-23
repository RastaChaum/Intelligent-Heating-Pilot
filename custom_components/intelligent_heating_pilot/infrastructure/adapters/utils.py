"""Shared utility functions for infrastructure adapters."""
from __future__ import annotations

from homeassistant.core import HomeAssistant


def get_entity_name(hass: HomeAssistant, entity_id: str) -> str:
    """Get the friendly name of an entity, falling back to entity_id.
    
    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to get name for
        
    Returns:
        Friendly name or entity_id if not found
    """
    state = hass.states.get(entity_id)
    if state:
        return state.attributes.get("friendly_name", entity_id)
    return entity_id
