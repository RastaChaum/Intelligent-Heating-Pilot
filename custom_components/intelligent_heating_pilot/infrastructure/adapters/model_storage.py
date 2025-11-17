"""Home Assistant model storage adapter.

This adapter implements IModelStorage by using Home Assistant's storage helper
to persist learned heating model data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...domain.interfaces import IModelStorage
from ...domain.value_objects import SlopeData

if TYPE_CHECKING:
    from typing import Any

_LOGGER = logging.getLogger(__name__)

# Storage configuration
STORAGE_VERSION = 2  # Bumped for timestamped slope data
STORAGE_KEY = "intelligent_heating_pilot_model"

# Default values
DEFAULT_HEATING_SLOPE = 2.0  # °C/h - Conservative default
MAX_HISTORY_SIZE = 100  # Keep last 100 slope samples
DEFAULT_RETENTION_DAYS = 30  # Keep slopes for 30 days by default


class HAModelStorage(IModelStorage):
    """Home Assistant implementation of model storage.
    
    Uses Home Assistant's Store helper to persist learned heating slopes
    and other model parameters. This adapter contains NO business logic -
    it only provides persistence.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        retention_days: int = DEFAULT_RETENTION_DAYS
    ) -> None:
        """Initialize the model storage adapter.
        
        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Number of days to retain slope data (default: 30)
        """
        self._hass = hass
        self._entry_id = entry_id
        self._retention_days = retention_days
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry_id}"
        )
        self._data: dict[str, Any] = {}
        self._loaded = False
    
    async def _ensure_loaded(self) -> None:
        """Ensure storage data is loaded and migrated if needed."""
        if self._loaded:
            return
        
        stored_data = await self._store.async_load()
        if stored_data:
            self._data = stored_data
            
            # Migrate from v1 to v2 format if needed
            if "historical_slopes" in self._data and isinstance(
                self._data["historical_slopes"], list
            ):
                if self._data["historical_slopes"] and isinstance(
                    self._data["historical_slopes"][0], (int, float)
                ):
                    _LOGGER.info("Migrating slope data from v1 to v2 format")
                    self._migrate_to_v2()
            
            _LOGGER.debug("Loaded model storage data (version %d)", STORAGE_VERSION)
        else:
            # Initialize with default structure (v2 format)
            self._data = {
                "slope_data_list": [],  # List of {timestamp, slope_value}
                "learned_heating_slope": DEFAULT_HEATING_SLOPE,
            }
            _LOGGER.debug("Initialized new model storage with defaults")
        
        # Clean old data
        await self._cleanup_old_data()
        
        self._loaded = True
    
    def _migrate_to_v2(self) -> None:
        """Migrate data from v1 (float list) to v2 (timestamped list).
        
        Assumes old slopes were recorded recently and assigns timestamps
        evenly distributed over the past retention period.
        """
        old_slopes = self._data.get("historical_slopes", [])
        if not old_slopes:
            self._data["slope_data_list"] = []
            return
        
        # Create timestamped entries with evenly distributed timestamps
        now = dt_util.now()
        time_span_days = min(self._retention_days, 7)  # Assume data is from last 7 days
        time_delta = timedelta(days=time_span_days) / len(old_slopes)
        
        slope_data_list = []
        for i, slope in enumerate(old_slopes):
            timestamp = now - timedelta(days=time_span_days) + (time_delta * i)
            slope_data_list.append({
                "timestamp": timestamp.isoformat(),
                "slope_value": float(slope),
            })
        
        self._data["slope_data_list"] = slope_data_list
        # Keep historical_slopes for backward compatibility during transition
        _LOGGER.info("Migrated %d slope entries to v2 format", len(slope_data_list))
    
    async def _cleanup_old_data(self) -> None:
        """Remove slope data older than retention period."""
        slope_data_list = self._data.get("slope_data_list", [])
        if not slope_data_list:
            return
        
        cutoff_time = dt_util.now() - timedelta(days=self._retention_days)
        original_count = len(slope_data_list)
        
        # Filter out old entries
        slope_data_list = [
            entry for entry in slope_data_list
            if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
        ]
        
        if len(slope_data_list) < original_count:
            removed = original_count - len(slope_data_list)
            _LOGGER.info("Cleaned up %d old slope entries (older than %d days)", 
                        removed, self._retention_days)
            self._data["slope_data_list"] = slope_data_list
            await self._store.async_save(self._data)
    
    async def save_slope_in_history(self, slope: float) -> None:
        """Persist a newly learned heating slope in history.
        
        DEPRECATED: Use save_slope_data() for timestamped storage.
        Creates a SlopeData with current timestamp and delegates.
        
        Only positive slopes (heating phases) are stored. The history
        is automatically trimmed to MAX_HISTORY_SIZE entries.
        
        Args:
            slope: Heating slope value in °C/hour
        """
        if slope <= 0:
            _LOGGER.debug(
                "Skipping non-positive slope (%.4f°C/h) - not a heating phase",
                slope
            )
            return
        
        # Create SlopeData with current timestamp
        slope_data = SlopeData(
            slope_value=slope,
            timestamp=dt_util.now()
        )
        
        await self.save_slope_data(slope_data)
    
    async def save_slope_data(self, slope_data: SlopeData) -> None:
        """Persist a timestamped slope measurement.
        
        Args:
            slope_data: Slope data with timestamp and value
        """
        await self._ensure_loaded()
        
        # Get slope data list
        slope_data_list = self._data.get("slope_data_list", [])
        
        # Add new entry
        slope_data_list.append({
            "timestamp": slope_data.timestamp.isoformat(),
            "slope_value": slope_data.slope_value,
        })
        
        # Trim to max size (keep most recent)
        if len(slope_data_list) > MAX_HISTORY_SIZE:
            slope_data_list = slope_data_list[-MAX_HISTORY_SIZE:]
        
        self._data["slope_data_list"] = slope_data_list
        
        # Recalculate learned heating slope from all positive slopes
        all_slopes = [entry["slope_value"] for entry in slope_data_list]
        lhs = self._calculate_robust_average(all_slopes)
        self._data["learned_heating_slope"] = lhs
        
        _LOGGER.debug(
            "Added slope %.2f°C/h at %s (total: %d samples, LHS: %.2f°C/h)",
            slope_data.slope_value,
            slope_data.timestamp.isoformat(),
            len(slope_data_list),
            lhs
        )
        
        # Persist to storage
        await self._store.async_save(self._data)
    
    async def get_slopes_in_history(self) -> list[float]:
        """Retrieve historical learned heating slopes (values only).
        
        DEPRECATED: Use get_all_slope_data() for timestamped data.
        
        Returns:
            List of learned slope values in °C/hour, ordered from oldest to newest.
        """
        await self._ensure_loaded()
        
        # Return from new format if available
        slope_data_list = self._data.get("slope_data_list", [])
        if slope_data_list:
            return [entry["slope_value"] for entry in slope_data_list]
        
        # Fallback to old format for backward compatibility
        return self._data.get("historical_slopes", []).copy()
    
    async def get_all_slope_data(self) -> list[SlopeData]:
        """Retrieve all historical slope data with timestamps.
        
        Returns:
            List of SlopeData objects, ordered from oldest to newest.
        """
        await self._ensure_loaded()
        
        slope_data_list = self._data.get("slope_data_list", [])
        
        result = []
        for entry in slope_data_list:
            try:
                result.append(SlopeData(
                    slope_value=entry["slope_value"],
                    timestamp=datetime.fromisoformat(entry["timestamp"])
                ))
            except (KeyError, ValueError) as e:
                _LOGGER.warning("Skipping invalid slope entry: %s", e)
                continue
        
        return result
    
    async def get_slopes_in_time_window(
        self,
        before_time: datetime,
        window_hours: float
    ) -> list[SlopeData]:
        """Retrieve slopes within a time window before a given time.
        
        Args:
            before_time: End of the time window (exclusive)
            window_hours: Size of the time window in hours
            
        Returns:
            List of SlopeData within the window, ordered from oldest to newest.
            Empty list if no data available in the window.
        """
        await self._ensure_loaded()
        
        # Calculate window start time
        start_time = before_time - timedelta(hours=window_hours)
        
        _LOGGER.debug(
            "Querying slopes in window: %s to %s (%.1f hours)",
            start_time.isoformat(),
            before_time.isoformat(),
            window_hours
        )
        
        slope_data_list = self._data.get("slope_data_list", [])
        
        # Filter entries within the time window
        result = []
        for entry in slope_data_list:
            try:
                timestamp = datetime.fromisoformat(entry["timestamp"])
                if start_time <= timestamp < before_time:
                    result.append(SlopeData(
                        slope_value=entry["slope_value"],
                        timestamp=timestamp
                    ))
            except (KeyError, ValueError) as e:
                _LOGGER.warning("Skipping invalid slope entry: %s", e)
                continue
        
        _LOGGER.debug("Found %d slopes in time window", len(result))
        return result
    
    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).
        
        Returns the learned heating slope calculated from all historical data,
        or the default value if no data is available.
        
        Returns:
            The learned heating slope in °C/hour.
        """
        await self._ensure_loaded()
        
        # Try new format first
        slope_data_list = self._data.get("slope_data_list", [])
        
        if slope_data_list:
            # Use all positive slopes from new format
            positive_slopes = [
                entry["slope_value"] for entry in slope_data_list
                if entry["slope_value"] > 0
            ]
        else:
            # Fallback to old format
            slopes = self._data.get("historical_slopes", [])
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
        self._data["slope_data_list"] = []
        self._data["learned_heating_slope"] = DEFAULT_HEATING_SLOPE
        
        # Also clear old format if present
        if "historical_slopes" in self._data:
            self._data["historical_slopes"] = []
        
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
