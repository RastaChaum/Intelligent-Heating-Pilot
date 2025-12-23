"""Home Assistant environment reader adapter.

Reads environmental state from Home Assistant entities (temperatures, humidity, etc.)
and converts them to domain value objects.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.value_objects import EnvironmentState
from ..vtherm_compat import get_vtherm_attribute
from .utils import get_entity_name

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class HAEnvironmentReader:
    """Reads environmental conditions from Home Assistant entities.
    
    Converts HA entity states into domain EnvironmentState value objects.
    No business logic - pure data translation.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        vtherm_entity_id: str,
        outdoor_temp_entity_id: str | None = None,
        humidity_in_entity_id: str | None = None,
        humidity_out_entity_id: str | None = None,
        cloud_cover_entity_id: str | None = None,
    ) -> None:
        """Initialize the environment reader.
        
        Args:
            hass: Home Assistant instance
            vtherm_entity_id: VTherm climate entity ID
            outdoor_temp_entity_id: Outdoor temperature sensor (optional)
            humidity_in_entity_id: Indoor humidity sensor (optional)
            humidity_out_entity_id: Outdoor humidity sensor (optional)
            cloud_cover_entity_id: Cloud coverage sensor (optional)
        """
        self._hass = hass
        self._vtherm_entity_id = vtherm_entity_id
        self._outdoor_temp_entity_id = outdoor_temp_entity_id
        self._humidity_in_entity_id = humidity_in_entity_id
        self._humidity_out_entity_id = humidity_out_entity_id
        self._cloud_cover_entity_id = cloud_cover_entity_id
        self._device_name = get_entity_name(hass, vtherm_entity_id)
    
    async def get_current_environment(self) -> EnvironmentState | None:
        """Read current environmental state from HA entities.
        
        Returns:
            EnvironmentState value object, or None if required data missing
        """
        # Get current indoor temperature from VTherm
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            _LOGGER.warning("[%s] VTherm entity not found", self._device_name)
            return None
        
        # Use v8.0.0+ compatible attribute access
        current_temp_raw = get_vtherm_attribute(vtherm_state, "current_temperature")
        if current_temp_raw is None:
            _LOGGER.warning("[%s] No current_temperature available", self._device_name)
            return None
        
        try:
            current_temp = float(current_temp_raw)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid current_temperature: %s", current_temp_raw)
            return None
        
        # Get outdoor temperature (required for EnvironmentState)
        outdoor_temp = self._get_float_state(self._outdoor_temp_entity_id)
        if outdoor_temp is None:
            # Fallback: use current temp if outdoor not available
            outdoor_temp = current_temp
            _LOGGER.debug("No outdoor temp available, using indoor temp as fallback")
        
        # Get humidity (required for EnvironmentState)
        humidity = self._get_float_state(self._humidity_in_entity_id)
        if humidity is None:
            # Default fallback humidity
            humidity = 50.0
            _LOGGER.debug("No indoor humidity available, using default 50%%")
        
        # Optional sensors
        outdoor_humidity = self._get_float_state(self._humidity_out_entity_id)
        cloud_coverage = self._get_float_state(self._cloud_cover_entity_id)
        
        return EnvironmentState(
            indoor_temperature=current_temp,
            outdoor_temp=outdoor_temp,
            indoor_humidity=humidity,
            timestamp=dt_util.now(),
            outdoor_humidity=outdoor_humidity,
            cloud_coverage=cloud_coverage,
        )
    
    def get_vtherm_slope(self) -> float | None:
        """Get current heating slope from VTherm.
        
        Returns:
            Current slope in °C/h, or None if not available
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return None
        
        # Use v8.0.0+ compatible attribute access
        slope_raw = get_vtherm_attribute(vtherm_state, "slope")
        if slope_raw is None:
            return None
        
        try:
            return float(slope_raw)
        except (ValueError, TypeError):
            return None
    
    def is_heating_active(self) -> bool:
        """Check if heating is currently active.
        
        According to requirements: heating is active when:
        1. hvac_mode == 'heat' (heating mode enabled)
        2. current_temperature < target_temperature (demand for heat)
        
        Returns:
            True if heating is ON, False otherwise
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return False
        
        # Check hvac_mode is 'heat'
        hvac_mode = vtherm_state.state
        if hvac_mode != "heat":
            return False
        
        # Check current temp is lower than target temp (v8.0.0+ compatible)
        current_temp = get_vtherm_attribute(vtherm_state, "current_temperature")
        target_temp = get_vtherm_attribute(vtherm_state, "temperature")
        
        if current_temp is None or target_temp is None:
            # If we can't determine temps, assume not heating
            return False
        
        try:
            return float(current_temp) < float(target_temp)
        except (ValueError, TypeError):
            return False
    
    def _get_float_state(self, entity_id: str | None) -> float | None:
        """Safely get float value from entity state.
        
        Args:
            entity_id: Entity ID to read
            
        Returns:
            Float value or None
        """
        if not entity_id:
            return None
        
        state = self._hass.states.get(entity_id)
        if not state:
            return None
        
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    # --- Accessors for application orchestration (historical data fetching) ---
    def get_hass(self):
        """Return the Home Assistant instance for adapters.
        
        Exposed for application layer orchestration that needs to construct
        historical data adapters. This keeps infrastructure concerns out of
        the domain while enabling coordinated use cases.
        """
        return self._hass

    def get_vtherm_entity_id(self) -> str:
        """Return the VTherm climate entity id."""
        return self._vtherm_entity_id

    def get_outdoor_temp_entity_id(self) -> str | None:
        """Return the outdoor temperature sensor entity id (optional)."""
        return self._outdoor_temp_entity_id

    def get_humidity_in_entity_id(self) -> str | None:
        """Return the indoor humidity sensor entity id (optional)."""
        return self._humidity_in_entity_id

    def get_humidity_out_entity_id(self) -> str | None:
        """Return the outdoor humidity sensor entity id (optional)."""
        return self._humidity_out_entity_id

    def get_cloud_cover_entity_id(self) -> str | None:
        """Return the cloud coverage sensor entity id (optional)."""
        return self._cloud_cover_entity_id
