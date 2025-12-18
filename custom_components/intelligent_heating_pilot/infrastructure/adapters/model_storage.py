"""Home Assistant model storage adapter.

This adapter implements IModelStorage by using Home Assistant's storage helper
to persist the learned heating slope (LHS).

NOTE: Individual slope data is no longer persisted here. Slopes are now extracted
directly from Home Assistant recorder via HeatingCycleService.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...domain.interfaces import IModelStorage

if TYPE_CHECKING:
    from typing import Any

_LOGGER = logging.getLogger(__name__)

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = "intelligent_heating_pilot_model"

# Default values
DEFAULT_HEATING_SLOPE = 2.0  # °C/h - Conservative default


class HAModelStorage(IModelStorage):
    """Home Assistant implementation of model storage.
    
    Uses Home Assistant's Store helper to persist the learned heating slope (LHS).
    This is a simplified adapter that only stores the global LHS value.
    
    Individual slope data extraction now comes from Home Assistant recorder
    via HeatingCycleService.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        retention_days: int = 30  # Kept for backward compatibility
    ) -> None:
        """Initialize the model storage adapter.
        
        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Deprecated - kept for backward compatibility
        """
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry_id}"
        )
        self._data: dict[str, Any] = {}
        self._loaded = False
    
    async def _ensure_loaded(self) -> None:
        """Ensure storage data is loaded."""
        if self._loaded:
            return
        
        stored_data = await self._store.async_load()
        if stored_data:
            self._data = stored_data
            _LOGGER.debug("Loaded model storage data (version %d)", STORAGE_VERSION)
        else:
            # Initialize with default structure
            self._data = {
                "learned_heating_slope": DEFAULT_HEATING_SLOPE,
            }
            _LOGGER.debug("Initialized new model storage with defaults")
        
        self._loaded = True
    
    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).
        
        Returns the global learned heating slope, or the default value if not available.
        This is now primarily used as a fallback when contextual LHS cannot be computed.
        
        Returns:
            The learned heating slope in °C/hour.
        """
        await self._ensure_loaded()
        
        lhs = self._data.get("learned_heating_slope")
        if lhs is None or lhs <= 0:
            _LOGGER.debug(
                "No learned heating slope in history, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        return lhs
    
    async def clear_slope_history(self) -> None:
        """Clear all learned slope data from history.
        
        This resets the learning system to its initial state.
        """
        await self._ensure_loaded()
        
        _LOGGER.info("Clearing all learned slope history")
        self._data["learned_heating_slope"] = DEFAULT_HEATING_SLOPE
        
        await self._store.async_save(self._data)
