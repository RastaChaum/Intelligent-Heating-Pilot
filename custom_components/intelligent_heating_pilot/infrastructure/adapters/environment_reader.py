"""Home Assistant environment reader adapter.

Reads environmental state from Home Assistant entities (temperatures, humidity, etc.)
and converts them to domain value objects.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from ...domain.interfaces import IEnvironmentReader
from ...domain.value_objects import EnvironmentState
from ..vtherm_compat import get_vtherm_room_temperature
from .utils import (
    WEATHER_ATTR_CLOUD_COVERAGE,
    WEATHER_ATTR_HUMIDITY,
    get_entity_name,
    read_numeric_state,
    read_temperature_celsius,
)

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class HAEnvironmentReader(IEnvironmentReader):
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
            outdoor_temp_entity_id: Outdoor temperature sensor or weather entity (optional)
            humidity_in_entity_id: Indoor humidity sensor (optional)
            humidity_out_entity_id: Outdoor humidity sensor or weather entity (optional)
            cloud_cover_entity_id: Cloud coverage sensor or weather entity (optional)
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

        # The smoothed room temperature: a raw reading toggling between two
        # adjacent values moved the anticipated start back and forth (#258).
        current_temp = get_vtherm_room_temperature(vtherm_state)
        if current_temp is None:
            _LOGGER.warning("[%s] No room temperature available", self._device_name)
            return None

        # Outdoor temperature is optional: a missing value stays None so the domain
        # skips the outdoor correction. Substituting the indoor temperature made it
        # apply a 10-20% correction computed from the wrong quantity.
        outdoor_temp_state = self._get_state(self._outdoor_temp_entity_id)
        outdoor_temp = read_temperature_celsius(outdoor_temp_state) if outdoor_temp_state else None

        # Get humidity (required for EnvironmentState)
        humidity = self._get_float_state(self._humidity_in_entity_id, WEATHER_ATTR_HUMIDITY)
        if humidity is None:
            # Default fallback humidity
            humidity = 50.0
            _LOGGER.debug("No indoor humidity available, using default 50%%")

        # Optional sensors
        outdoor_humidity = self._get_float_state(
            self._humidity_out_entity_id, WEATHER_ATTR_HUMIDITY
        )
        cloud_coverage = self._get_float_state(
            self._cloud_cover_entity_id, WEATHER_ATTR_CLOUD_COVERAGE
        )

        return EnvironmentState(
            indoor_temperature=current_temp,
            outdoor_temp=outdoor_temp,
            indoor_humidity=humidity,
            timestamp=dt_util.now(),
            outdoor_humidity=outdoor_humidity,
            cloud_coverage=cloud_coverage,
        )

    def _get_float_state(self, entity_id: str | None, weather_attribute: str) -> float | None:
        """Safely get float value from entity state.

        Args:
            entity_id: Entity ID to read
            weather_attribute: Attribute to read if the entity is a weather entity

        Returns:
            Float value or None
        """
        state = self._get_state(entity_id)
        return read_numeric_state(state, weather_attribute) if state else None

    def _get_state(self, entity_id: str | None) -> State | None:
        """Return the entity state, or None when unset or missing."""
        if not entity_id:
            return None
        return self._hass.states.get(entity_id)
