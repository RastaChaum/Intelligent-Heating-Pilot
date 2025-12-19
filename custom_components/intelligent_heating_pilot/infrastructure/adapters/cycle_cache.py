"""Home Assistant cycle cache adapter.

This adapter implements ICycleCache by using Home Assistant's storage helper
to persist heating cycles with incremental update support.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...domain.interfaces.cycle_cache import ICycleCache
from ...domain.value_objects.cycle_cache_data import CycleCacheData
from ...domain.value_objects.heating import HeatingCycle, TariffPeriodDetail

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = "intelligent_heating_pilot_cycle_cache"

# Default retention for cycles (days)
DEFAULT_RETENTION_DAYS = 30


class HACycleCache(ICycleCache):
    """Home Assistant implementation of cycle cache storage.
    
    Uses Home Assistant's Store helper to persist heating cycles with
    metadata for incremental updates. Cycles are stored per device
    and automatically pruned based on retention settings.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        """Initialize the cycle cache adapter.
        
        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Number of days to retain cycles (default: 30)
        """
        _LOGGER.info("Entering HACycleCache.__init__")
        _LOGGER.debug(
            "Initializing with entry_id=%s, retention_days=%s",
            entry_id,
            retention_days,
        )
        
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
        
        _LOGGER.info("Exiting HACycleCache.__init__")
    
    async def _ensure_loaded(self) -> None:
        """Ensure storage data is loaded."""
        if self._loaded:
            return
        
        _LOGGER.info("Entering HACycleCache._ensure_loaded")
        
        stored_data = await self._store.async_load()
        if stored_data:
            self._data = stored_data
            _LOGGER.debug(
                "Loaded cycle cache data (version %d) with %d devices",
                STORAGE_VERSION,
                len(self._data)
            )
        else:
            # Initialize with empty structure
            self._data = {}
            _LOGGER.debug("Initialized new cycle cache storage")
        
        self._loaded = True
        
        _LOGGER.info("Exiting HACycleCache._ensure_loaded")
    
    async def get_cache_data(self, device_id: str) -> CycleCacheData | None:
        """Get cached cycle data for a device.
        
        Args:
            device_id: The device identifier
            
        Returns:
            CycleCacheData if cache exists, None otherwise
        """
        _LOGGER.info("Entering HACycleCache.get_cache_data")
        _LOGGER.debug("Getting cache data for device_id=%s", device_id)
        
        await self._ensure_loaded()
        
        device_data = self._data.get(device_id)
        if not device_data:
            _LOGGER.debug("No cache found for device_id=%s", device_id)
            _LOGGER.info("Exiting HACycleCache.get_cache_data")
            return None
        
        # Deserialize cycles
        cycles = self._deserialize_cycles(device_data.get("cycles", []))
        last_search_time = self._parse_timestamp(device_data.get("last_search_time"))
        retention_days = device_data.get("retention_days", self._retention_days)
        
        if last_search_time is None:
            _LOGGER.warning("Invalid last_search_time in cache for device %s", device_id)
            _LOGGER.info("Exiting HACycleCache.get_cache_data")
            return None
        
        cache_data = CycleCacheData(
            device_id=device_id,
            cycles=tuple(cycles),
            last_search_time=last_search_time,
            retention_days=retention_days,
        )
        
        _LOGGER.debug(
            "Retrieved cache with %d cycles, last_search_time=%s",
            len(cycles),
            last_search_time,
        )
        _LOGGER.info("Exiting HACycleCache.get_cache_data")
        
        return cache_data
    
    async def append_cycles(
        self,
        device_id: str,
        new_cycles: list[HeatingCycle],
        search_end_time: datetime,
    ) -> None:
        """Append new cycles to the cache and update search timestamp.
        
        Args:
            device_id: The device identifier
            new_cycles: List of new cycles to append
            search_end_time: Timestamp marking the end of this search period
        """
        _LOGGER.info("Entering HACycleCache.append_cycles")
        _LOGGER.debug(
            "Appending %d cycles for device_id=%s, search_end_time=%s",
            len(new_cycles),
            device_id,
            search_end_time,
        )
        
        await self._ensure_loaded()
        
        # Get existing cache or initialize
        existing_cache = await self.get_cache_data(device_id)
        
        if existing_cache:
            existing_cycles = list(existing_cache.cycles)
        else:
            existing_cycles = []
        
        # Deduplicate: Use (start_time, device_id) as key
        existing_keys = {
            (cycle.start_time, cycle.device_id)
            for cycle in existing_cycles
        }
        
        # Add only new cycles
        unique_new_cycles = [
            cycle for cycle in new_cycles
            if (cycle.start_time, cycle.device_id) not in existing_keys
        ]
        
        # Combine and sort by start_time
        all_cycles = existing_cycles + unique_new_cycles
        all_cycles.sort(key=lambda c: c.start_time)
        
        # Update storage
        self._data[device_id] = {
            "cycles": self._serialize_cycles(all_cycles),
            "last_search_time": search_end_time.isoformat(),
            "retention_days": self._retention_days,
        }
        
        await self._store.async_save(self._data)
        
        _LOGGER.debug(
            "Appended %d unique cycles (total now: %d) for device %s",
            len(unique_new_cycles),
            len(all_cycles),
            device_id,
        )
        _LOGGER.info("Exiting HACycleCache.append_cycles")
    
    async def prune_old_cycles(
        self,
        device_id: str,
        reference_time: datetime,
    ) -> None:
        """Remove cycles older than the retention period.
        
        Args:
            device_id: The device identifier
            reference_time: Time to calculate retention from
        """
        _LOGGER.info("Entering HACycleCache.prune_old_cycles")
        _LOGGER.debug(
            "Pruning cycles for device_id=%s, reference_time=%s",
            device_id,
            reference_time,
        )
        
        await self._ensure_loaded()
        
        cache_data = await self.get_cache_data(device_id)
        if not cache_data:
            _LOGGER.debug("No cache to prune for device %s", device_id)
            _LOGGER.info("Exiting HACycleCache.prune_old_cycles")
            return
        
        cutoff_time = reference_time - timedelta(days=cache_data.retention_days)
        
        # Filter cycles within retention
        retained_cycles = [
            cycle for cycle in cache_data.cycles
            if cycle.start_time >= cutoff_time
        ]
        
        removed_count = len(cache_data.cycles) - len(retained_cycles)
        
        if removed_count > 0:
            # Update storage
            self._data[device_id] = {
                "cycles": self._serialize_cycles(retained_cycles),
                "last_search_time": cache_data.last_search_time.isoformat(),
                "retention_days": cache_data.retention_days,
            }
            
            await self._store.async_save(self._data)
            
            _LOGGER.debug(
                "Pruned %d cycles older than %s (retained %d)",
                removed_count,
                cutoff_time,
                len(retained_cycles),
            )
        else:
            _LOGGER.debug("No cycles to prune for device %s", device_id)
        
        _LOGGER.info("Exiting HACycleCache.prune_old_cycles")
    
    async def clear_cache(self, device_id: str) -> None:
        """Clear all cached cycles for a device.
        
        Args:
            device_id: The device identifier
        """
        _LOGGER.info("Entering HACycleCache.clear_cache")
        _LOGGER.debug("Clearing cache for device_id=%s", device_id)
        
        await self._ensure_loaded()
        
        if device_id in self._data:
            del self._data[device_id]
            await self._store.async_save(self._data)
            _LOGGER.debug("Cleared cache for device %s", device_id)
        else:
            _LOGGER.debug("No cache to clear for device %s", device_id)
        
        _LOGGER.info("Exiting HACycleCache.clear_cache")
    
    async def get_last_search_time(self, device_id: str) -> datetime | None:
        """Get the timestamp of the last cycle search.
        
        Args:
            device_id: The device identifier
            
        Returns:
            UTC timestamp of last search, or None if no cache exists
        """
        _LOGGER.info("Entering HACycleCache.get_last_search_time")
        _LOGGER.debug("Getting last search time for device_id=%s", device_id)
        
        cache_data = await self.get_cache_data(device_id)
        
        result = cache_data.last_search_time if cache_data else None
        
        _LOGGER.debug("Last search time for device %s: %s", device_id, result)
        _LOGGER.info("Exiting HACycleCache.get_last_search_time")
        
        return result
    
    def _serialize_cycles(self, cycles: list[HeatingCycle]) -> list[dict[str, Any]]:
        """Serialize HeatingCycle objects to JSON-compatible dicts.
        
        Args:
            cycles: List of HeatingCycle objects
            
        Returns:
            List of serialized cycle dictionaries
        """
        serialized = []
        for cycle in cycles:
            cycle_dict = {
                "device_id": cycle.device_id,
                "start_time": cycle.start_time.isoformat(),
                "end_time": cycle.end_time.isoformat(),
                "target_temp": cycle.target_temp,
                "end_temp": cycle.end_temp,
                "start_temp": cycle.start_temp,
                "tariff_details": None,
            }
            
            # Serialize tariff details if present
            if cycle.tariff_details:
                cycle_dict["tariff_details"] = [
                    {
                        "tariff_price_eur_per_kwh": td.tariff_price_eur_per_kwh,
                        "energy_kwh": td.energy_kwh,
                        "heating_duration_minutes": td.heating_duration_minutes,
                        "cost_euro": td.cost_euro,
                    }
                    for td in cycle.tariff_details
                ]
            
            serialized.append(cycle_dict)
        
        return serialized
    
    def _deserialize_cycles(self, cycle_dicts: list[dict[str, Any]]) -> list[HeatingCycle]:
        """Deserialize JSON-compatible dicts to HeatingCycle objects.
        
        Args:
            cycle_dicts: List of serialized cycle dictionaries
            
        Returns:
            List of HeatingCycle objects
        """
        cycles = []
        for cycle_dict in cycle_dicts:
            try:
                # Deserialize tariff details if present
                tariff_details = None
                if cycle_dict.get("tariff_details"):
                    tariff_details = [
                        TariffPeriodDetail(
                            tariff_price_eur_per_kwh=td["tariff_price_eur_per_kwh"],
                            energy_kwh=td["energy_kwh"],
                            heating_duration_minutes=td["heating_duration_minutes"],
                            cost_euro=td["cost_euro"],
                        )
                        for td in cycle_dict["tariff_details"]
                    ]
                
                cycle = HeatingCycle(
                    device_id=cycle_dict["device_id"],
                    start_time=self._parse_timestamp(cycle_dict["start_time"]),
                    end_time=self._parse_timestamp(cycle_dict["end_time"]),
                    target_temp=cycle_dict["target_temp"],
                    end_temp=cycle_dict["end_temp"],
                    start_temp=cycle_dict["start_temp"],
                    tariff_details=tariff_details,
                )
                cycles.append(cycle)
            except (KeyError, ValueError, TypeError) as exc:
                _LOGGER.warning("Failed to deserialize cycle: %s", exc)
                continue
        
        return cycles
    
    def _parse_timestamp(self, timestamp_str: str | None) -> datetime:
        """Parse ISO timestamp string to timezone-aware datetime.
        
        Args:
            timestamp_str: ISO format timestamp string
            
        Returns:
            Timezone-aware datetime object
            
        Raises:
            ValueError: If timestamp cannot be parsed
        """
        if not timestamp_str:
            raise ValueError("Timestamp string is empty")
        
        dt = datetime.fromisoformat(timestamp_str)
        
        # Ensure timezone-aware
        if dt.tzinfo is None:
            from homeassistant.util import dt as dt_util
            dt = dt_util.as_utc(dt)
        
        return dt
