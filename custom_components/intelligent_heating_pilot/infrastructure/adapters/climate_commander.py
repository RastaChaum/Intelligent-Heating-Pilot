"""Home Assistant climate commander adapter.

This adapter implements the ability to control climate entities (VTherm)
from the domain layer.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class HAClimateCommander:
    """Controls climate entities (VTherm) from domain layer.
    
    This adapter translates domain heating control commands into
    Home Assistant climate service calls. No business logic.
    """
    
    def __init__(self, hass: HomeAssistant, climate_entity_id: str) -> None:
        """Initialize the climate commander.
        
        Args:
            hass: Home Assistant instance
            climate_entity_id: The VTherm/climate entity to control
        """
        self._hass = hass
        self._climate_entity_id = climate_entity_id
    
    async def set_temperature(self, target_temp: float) -> None:
        """Set target temperature for the climate entity.
        
        Args:
            target_temp: Target temperature in Celsius
        """
        _LOGGER.info(
            "Setting %s temperature to %.1f°C",
            self._climate_entity_id,
            target_temp
        )
        
        await self._hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": self._climate_entity_id,
                "temperature": target_temp,
            },
            blocking=True,
        )
    
    async def set_hvac_mode(self, mode: str) -> None:
        """Set HVAC mode (heat, off, etc.).
        
        Args:
            mode: HVAC mode (heat, off, auto, etc.)
        """
        _LOGGER.info(
            "Setting %s HVAC mode to %s",
            self._climate_entity_id,
            mode
        )
        
        await self._hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {
                "entity_id": self._climate_entity_id,
                "hvac_mode": mode,
            },
            blocking=True,
        )
    
    async def turn_off(self) -> None:
        """Turn off heating."""
        await self.set_hvac_mode("off")
    
    async def turn_on_heat(self, target_temp: float) -> None:
        """Turn on heating with target temperature.
        
        Args:
            target_temp: Target temperature in Celsius
        """
        await self.set_hvac_mode("heat")
        await self.set_temperature(target_temp)
