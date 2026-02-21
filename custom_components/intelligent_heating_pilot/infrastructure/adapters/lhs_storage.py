"""Home Assistant LHS (Learned Heating Slope) storage adapter.

This adapter implements ILhsStorage by using Home Assistant's storage helper
to persist the learned heating slope (LHS).

NOTE: Individual slope data is no longer persisted here. Slopes are now extracted
directly from Home Assistant recorder via HeatingCycleService.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...domain.interfaces import ILhsStorage
from ...domain.value_objects.lhs_cache_entry import LHSCacheEntry
from .base_ha_storage import BaseHAStorageAdapter

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Storage key
STORAGE_KEY = "intelligent_heating_pilot_lhs"

# Default values
DEFAULT_HEATING_SLOPE = 2.0  # °C/h - Conservative default


class HALhsStorage(BaseHAStorageAdapter[dict[str, Any]], ILhsStorage):
    """Home Assistant implementation of LHS storage.

    Uses Home Assistant's Store helper to persist the learned heating slope (LHS).
    This is a simplified adapter that only stores the global LHS value.

    Individual slope data extraction now comes from Home Assistant recorder
    via HeatingCycleService.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        retention_days: int = 30,
    ) -> None:
        """Initialize the LHS storage adapter.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Number of days to retain LHS cache data.
                When 0, caching is disabled and default LHS is always used.
        """
        super().__init__(
            hass=hass,
            entry_id=entry_id,
            storage_key=STORAGE_KEY,
            retention_days=retention_days,
        )

        if self._is_caching_disabled():
            _LOGGER.debug(
                "LHS storage initialized with retention_days=0 (caching disabled for %s)",
                entry_id,
            )

    def _get_default_data(self) -> dict[str, Any]:
        """Return default data structure for LHS storage.

        Returns:
            Default dictionary with learned_heating_slope
        """
        return {
            "learned_heating_slope": DEFAULT_HEATING_SLOPE,
            "learned_dead_time": None,
        }

    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).

        Returns the global learned heating slope, or the default value if not available.
        When retention_days=0, caching is disabled and default value is always returned.
        This is now primarily used as a fallback when contextual LHS cannot be computed.

        Returns:
            The learned heating slope in °C/hour.
        """
        # When retention is disabled, return default immediately without loading
        if self._is_caching_disabled():
            _LOGGER.debug(
                "Retention disabled (retention_days=%d), returning default LHS: %.2f°C/h",
                self._retention_days,
                DEFAULT_HEATING_SLOPE,
            )
            return DEFAULT_HEATING_SLOPE

        await self._ensure_loaded()

        from typing import cast

        # First, try to get the cached global LHS (set by extract_heating_cycles_use_case)
        cached_entry_data = self._data.get("cached_global_lhs")
        if cached_entry_data and isinstance(cached_entry_data, dict):
            cached_lhs = cached_entry_data.get("value")
            if cached_lhs is not None and cached_lhs > 0:
                _LOGGER.debug(
                    "Returning cached global LHS: %.2f°C/h",
                    cached_lhs,
                )
                return cast(float, cached_lhs)

        # Fallback to legacy learned_heating_slope (for backward compatibility)
        lhs = self._data.get("learned_heating_slope")
        if lhs is None or lhs <= 0:
            _LOGGER.debug(
                "No learned heating slope in history, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE,
            )
            return DEFAULT_HEATING_SLOPE

        return cast(float, lhs)

    async def clear_slope_history(self) -> None:
        """Clear all learned slope data from history.

        This resets the learning system to its initial state.
        """
        await self._ensure_loaded()

        _LOGGER.info("Clearing all learned slope history")
        self._data["learned_heating_slope"] = DEFAULT_HEATING_SLOPE

        await self._save_data()

    async def get_cached_global_lhs(self) -> LHSCacheEntry | None:
        """Return cached global LHS if available.

        When retention_days=0 (caching disabled), always returns None.
        This forces the use of default LHS values.
        """
        if self._is_caching_disabled():
            _LOGGER.debug(
                "Caching disabled (retention_days=0), returning None for cached global LHS"
            )
            return None

        await self._ensure_loaded()
        return self._deserialize_lhs_cache_entry(self._data.get("cached_global_lhs"))

    async def set_cached_global_lhs(self, lhs: float, updated_at: datetime) -> None:
        """Persist global LHS cache with timestamp."""

        await self._ensure_loaded()
        self._data["cached_global_lhs"] = self._serialize_lhs_cache_entry(lhs, updated_at)
        await self._save_data()

    async def get_cached_contextual_lhs(self, hour: int) -> LHSCacheEntry | None:
        """Return cached contextual LHS for the given hour if available."""

        if self._is_caching_disabled():
            _LOGGER.debug(
                "Caching disabled (retention_days=0), returning None for cached contextual LHS"
            )
            return None

        await self._ensure_loaded()
        contextual_cache = self._data.get("cached_contextual_lhs") or {}
        entry = contextual_cache.get(str(hour))
        return self._deserialize_lhs_cache_entry(entry, hour=hour)

    async def set_cached_contextual_lhs(self, hour: int, lhs: float, updated_at: datetime) -> None:
        """Persist contextual LHS cache for the given hour with timestamp."""

        if self._is_caching_disabled():
            _LOGGER.debug("Caching disabled (retention_days=0), skipping contextual LHS cache set")
            return

        await self._ensure_loaded()
        contextual_cache = self._data.setdefault("cached_contextual_lhs", {})
        contextual_cache[str(hour)] = self._serialize_lhs_cache_entry(lhs, updated_at)
        await self._save_data()

    async def clear_contextual_cache(self) -> None:
        """Clear all cached contextual LHS entries."""

        await self._ensure_loaded()
        self._data["cached_contextual_lhs"] = {}
        await self._save_data()

    async def get_learned_dead_time(self) -> float | None:
        """Get the learned dead time value from auto-learning.

        Returns:
            Dead time in minutes, or None if not yet learned
        """
        await self._ensure_loaded()
        return self._data.get("learned_dead_time")

    async def set_learned_dead_time(self, dead_time: float | None) -> None:
        """Persist learned dead time value from auto-learning.

        Args:
            dead_time: Dead time in minutes, or None to clear
        """
        await self._ensure_loaded()
        self._data["learned_dead_time"] = dead_time
        await self._save_data()
        _LOGGER.info("Learned dead time updated: %.1f minutes", dead_time or 0)

    def _serialize_lhs_cache_entry(self, lhs: float, updated_at: datetime) -> dict[str, Any]:
        """Serialize an LHS cache entry to a dictionary for storage.

        Args:
            lhs: The LHS value to cache
            updated_at: The timestamp when the LHS was calculated

        Returns:
            A dictionary representation suitable for JSON storage
        """
        return {
            "value": lhs,
            "updated_at": self._serialize_datetime(updated_at),
        }

    def _deserialize_lhs_cache_entry(
        self, data: dict[str, Any] | None, hour: int | None = None
    ) -> LHSCacheEntry | None:
        """Deserialize a stored cache entry into an LHSCacheEntry object.

        Args:
            data: The stored dictionary data
            hour: Optional hour context for contextual LHS

        Returns:
            An LHSCacheEntry object if data is valid, None otherwise
        """
        if not data:
            return None

        try:
            value = data.get("value")
            updated_at_str = data.get("updated_at")

            if value is None or updated_at_str is None:
                return None

            updated_at = self._parse_datetime(updated_at_str)
            return LHSCacheEntry(value=value, updated_at=updated_at, hour=hour)
        except (ValueError, TypeError, KeyError) as e:
            _LOGGER.warning("Failed to deserialize cached LHS entry: %s", e)
            return None
