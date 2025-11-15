"""Home Assistant model storage adapter.

This adapter implements IModelStorage by using Home Assistant's storage helper
to persist learned heating model data.
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
MAX_HISTORY_SIZE = 100  # Keep last 100 slope samples


class HAModelStorage(IModelStorage):
    """Home Assistant implementation of model storage.
    
    Uses Home Assistant's Store helper to persist learned heating slopes
    and other model parameters. This adapter contains NO business logic -
    it only provides persistence.
    """
    
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the model storage adapter.
        
        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
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
            _LOGGER.debug("Loaded model storage data: %s", self._data)
        else:
            # Initialize with default structure
            self._data = {
                "historical_slopes": [],
                "learned_heating_slope": DEFAULT_HEATING_SLOPE,
            }
            _LOGGER.debug("Initialized new model storage with defaults")
        
        self._loaded = True
    
    async def save_slope_in_history(self, slope: float) -> None:
        """Persist a newly learned heating slope in history.
        
        Only positive slopes (heating phases) are stored. The history
        is automatically trimmed to MAX_HISTORY_SIZE entries.
        
        Args:
            slope: Heating slope value in °C/hour
        """
        await self._ensure_loaded()
        
        # Only store positive slopes (heating phases)
        if slope <= 0:
            _LOGGER.debug(
                "Skipping non-positive slope (%.4f°C/h) - not a heating phase",
                slope
            )
            return
        
        # Add to history
        slopes = self._data.get("historical_slopes", [])
        slopes.append(slope)
        
        # Trim to max size
        if len(slopes) > MAX_HISTORY_SIZE:
            slopes = slopes[-MAX_HISTORY_SIZE:]
        
        self._data["historical_slopes"] = slopes
        
        # Recalculate learned heating slope
        lhs = self._calculate_robust_average(slopes)
        self._data["learned_heating_slope"] = lhs
        
        _LOGGER.debug(
            "Added slope %.2f°C/h to history (total: %d samples, LHS: %.2f°C/h)",
            slope,
            len(slopes),
            lhs
        )
        
        # Persist to storage
        await self._store.async_save(self._data)
    
    async def get_slopes_in_history(self) -> list[float]:
        """Retrieve historical learned heating slopes.
        
        Returns:
            List of learned slope values in °C/hour, ordered from oldest to newest.
        """
        await self._ensure_loaded()
        return self._data.get("historical_slopes", []).copy()
    
    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).
        
        Returns the learned heating slope calculated from historical data,
        or the default value if no data is available.
        
        Returns:
            The learned heating slope in °C/hour.
        """
        await self._ensure_loaded()
        
        slopes = self._data.get("historical_slopes", [])
        
        # Filter out negative slopes (cooling phases)
        positive_slopes = [s for s in slopes if s > 0]
        
        if not positive_slopes:
            _LOGGER.debug(
                "No positive learned slopes in history, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Get cached LHS or recalculate
        lhs = self._data.get("learned_heating_slope")
        if lhs is None or lhs <= 0:
            lhs = self._calculate_robust_average(positive_slopes)
            self._data["learned_heating_slope"] = lhs
            _LOGGER.debug(
                "Recalculated LHS from %d positive samples: %.2f°C/h",
                len(positive_slopes),
                lhs
            )
        else:
            _LOGGER.debug(
                "Using cached LHS: %.2f°C/h (from %d positive samples)",
                lhs,
                len(positive_slopes)
            )
        
        return lhs
    
    async def clear_slope_history(self) -> None:
        """Clear all learned slope data from history.
        
        This resets the learning system to its initial state.
        """
        await self._ensure_loaded()
        
        _LOGGER.info("Clearing all learned slope history")
        self._data["historical_slopes"] = []
        self._data["learned_heating_slope"] = DEFAULT_HEATING_SLOPE
        
        await self._store.async_save(self._data)
    
    def _calculate_robust_average(self, values: list[float]) -> float:
        """Calculate robust average by removing extreme values (trimmed mean).
        
        This method provides a more stable estimate by removing outliers.
        
        Args:
            values: List of slope values
            
        Returns:
            Robust average of the values
        """
        if not values:
            return DEFAULT_HEATING_SLOPE
        
        # Sort values
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        if n < 4:
            # Not enough data for trimming, use simple average
            return sum(sorted_values) / n
        
        # Remove top and bottom 10% (trimmed mean)
        trim_count = max(1, int(n * 0.1))
        trimmed = sorted_values[trim_count:-trim_count]
        
        if not trimmed:
            # Fallback to median if trimming removed everything
            return sorted_values[n // 2]
        
        return sum(trimmed) / len(trimmed)
