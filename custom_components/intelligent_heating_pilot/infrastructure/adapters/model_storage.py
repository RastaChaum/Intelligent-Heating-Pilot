"""Home Assistant model storage adapter.

This adapter implements IModelStorage by using Home Assistant's storage helper
to persist the learned heating slope (LHS).

NOTE: Individual slope data is no longer persisted here. Slopes are now extracted
directly from Home Assistant recorder via HeatingCycleService.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...domain.interfaces.model_storage_interface import IModelStorage
from ...domain.value_objects.lhs_cache_entry import LHSCacheEntry

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
        retention_days: int = 30,
    ) -> None:
        """Initialize the model storage adapter.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Number of days to retain LHS cache data.
                When 0, caching is disabled and default LHS is always used.
        """
        self._hass = hass
        self._entry_id = entry_id
        self._retention_days = retention_days
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._data: dict[str, Any] = {}
        self._loaded = False

        if retention_days == 0:
            _LOGGER.debug(
                "Model storage initialized with retention_days=0 (caching disabled for %s)",
                entry_id,
            )

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
        When retention_days=0, caching is disabled and default value is always returned.
        This is now primarily used as a fallback when contextual LHS cannot be computed.

        Returns:
            The learned heating slope in °C/hour.
        """
        # When retention is disabled, return default immediately without loading
        if self._retention_days <= 0:
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

        await self._store.async_save(self._data)

    async def get_cached_global_lhs(self) -> LHSCacheEntry | None:
        """Return cached global LHS if available.

        When retention_days=0 (caching disabled), always returns None.
        This forces the use of default LHS values.
        """
        if self._retention_days == 0:
            _LOGGER.debug(
                "Caching disabled (retention_days=0), returning None for cached global LHS"
            )
            return None

        await self._ensure_loaded()
        return self._deserialize_cached_entry(self._data.get("cached_global_lhs"))

    async def set_cached_global_lhs(self, lhs: float, updated_at: datetime) -> None:
        """Persist global LHS cache with timestamp."""

        await self._ensure_loaded()
        self._data["cached_global_lhs"] = self._serialize_cached_entry(lhs, updated_at)
        await self._store.async_save(self._data)

    async def get_cached_contextual_lhs(self, hour: int) -> LHSCacheEntry | None:
        """Return cached contextual LHS for the given hour if available."""

        if self._retention_days == 0:
            _LOGGER.debug(
                "Caching disabled (retention_days=0), returning None for cached contextual LHS"
            )
            return None

        await self._ensure_loaded()
        contextual_cache = self._data.get("cached_contextual_lhs") or {}
        entry = contextual_cache.get(str(hour))
        return self._deserialize_cached_entry(entry, hour=hour)

    async def set_cached_contextual_lhs(self, hour: int, lhs: float, updated_at: datetime) -> None:
        """Persist contextual LHS cache for the given hour with timestamp."""

        if self._retention_days == 0:
            _LOGGER.debug("Caching disabled (retention_days=0), skipping contextual LHS cache set")
            return

        await self._ensure_loaded()
        contextual_cache = self._data.setdefault("cached_contextual_lhs", {})
        contextual_cache[str(hour)] = self._serialize_cached_entry(lhs, updated_at)
        await self._store.async_save(self._data)

    async def clear_contextual_cache(self) -> None:
        """Clear all cached contextual LHS entries."""

        await self._ensure_loaded()
        self._data["cached_contextual_lhs"] = {}
        await self._store.async_save(self._data)

    def _serialize_cached_entry(self, lhs: float, updated_at: datetime) -> dict[str, Any]:
        """Serialize an LHS cache entry to a dictionary for storage.

        Args:
            lhs: The LHS value to cache
            updated_at: The timestamp when the LHS was calculated

        Returns:
            A dictionary representation suitable for JSON storage
        """
        return {
            "value": lhs,
            "updated_at": updated_at.isoformat(),
        }

    def _deserialize_cached_entry(
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

            updated_at = datetime.fromisoformat(updated_at_str)
            return LHSCacheEntry(value=value, updated_at=updated_at, hour=hour)
        except (ValueError, TypeError, KeyError) as e:
            _LOGGER.warning("Failed to deserialize cached LHS entry: %s", e)
            return None
