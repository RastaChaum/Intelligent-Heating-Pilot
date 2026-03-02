"""Home Assistant heating cycle storage adapter.

This adapter implements IHeatingCycleStorage by using Home Assistant's storage helper
to persist heating cycles with incremental update support.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...domain.interfaces import IHeatingCycleStorage
from ...domain.value_objects import HeatingCycleCacheData
from ...domain.value_objects.heating import HeatingCycle, TariffPeriodDetail
from .base_ha_storage import BaseHAStorageAdapter

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Storage key
STORAGE_KEY = "intelligent_heating_pilot_heating_cycle"

# Default retention for cycles (days)
DEFAULT_RETENTION_DAYS = 30


class HAHeatingCycleStorage(BaseHAStorageAdapter[dict[str, Any]], IHeatingCycleStorage):
    """Home Assistant implementation of heating cycle storage.

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
        """Initialize the heating cycle storage adapter.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            retention_days: Number of days to retain cycles (default: 30)
        """
        super().__init__(
            hass=hass,
            entry_id=entry_id,
            storage_key=STORAGE_KEY,
            retention_days=retention_days,
        )

        _LOGGER.debug(
            "Initializing HAHeatingCycleStorage with entry_id=%s, retention_days=%s",
            entry_id,
            retention_days,
        )

    def _get_default_data(self) -> dict[str, Any]:
        """Return default data structure for heating cycle storage.

        Returns:
            Empty dictionary for device cycle data
        """
        return {}

    async def get_cache_data(self, device_id: str) -> HeatingCycleCacheData | None:
        """Get cached cycle data for a device.

        Args:
            device_id: The device identifier

        Returns:
            HeatingCycleCacheData if cache exists, None otherwise
        """
        _LOGGER.debug("Entering HAHeatingCycleStorage.get_cache_data")
        _LOGGER.debug("Getting cache data for device_id=%s", device_id)

        await self._ensure_loaded()

        device_data = self._data.get(device_id)
        if not device_data:
            _LOGGER.debug("No cache found for device_id=%s", device_id)
            _LOGGER.debug("Exiting HAHeatingCycleStorage.get_cache_data")
            return None

        # Deserialize cycles
        cycles = self._deserialize_heating_cycles(device_data.get("cycles", []))
        last_search_time_str = device_data.get("last_search_time")

        if not last_search_time_str:
            _LOGGER.warning("Invalid last_search_time in cache for device %s", device_id)
            _LOGGER.debug("Exiting HAHeatingCycleStorage.get_cache_data")
            return None

        try:
            last_search_time = self._parse_datetime(last_search_time_str)
        except ValueError as e:
            _LOGGER.warning("Failed to parse last_search_time for device %s: %s", device_id, e)
            _LOGGER.debug("Exiting HAHeatingCycleStorage.get_cache_data")
            return None

        retention_days = device_data.get("retention_days", self._retention_days)

        cache_data = HeatingCycleCacheData(
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
        _LOGGER.debug("Exiting HAHeatingCycleStorage.get_cache_data")

        return cache_data

    async def append_cycles(
        self,
        device_id: str,
        new_cycles: list[HeatingCycle],
        search_end_time: datetime,
        retention_days: int | None = None,
    ) -> None:
        """Append new cycles to the cache and update search timestamp.

        Args:
            device_id: The device identifier
            new_cycles: List of new cycles to append
            search_end_time: Timestamp marking the end of this search period
            retention_days: Optional retention days to store with cache metadata
        """
        _LOGGER.debug("Entering HAHeatingCycleStorage.append_cycles")
        _LOGGER.debug(
            "Appending %d cycles for device_id=%s, search_end_time=%s, retention_days=%s",
            len(new_cycles),
            device_id,
            search_end_time,
            retention_days,
        )

        await self._ensure_loaded()

        # Get existing cache or initialize
        existing_cache = await self.get_cache_data(device_id)

        existing_cycles = list(existing_cache.cycles) if existing_cache else []

        # Deduplicate: Use (start_time, device_id) as key
        existing_keys = {(cycle.start_time, cycle.device_id) for cycle in existing_cycles}

        # Add only new cycles
        unique_new_cycles = [
            cycle
            for cycle in new_cycles
            if (cycle.start_time, cycle.device_id) not in existing_keys
        ]

        # Combine and sort by start_time
        all_cycles = existing_cycles + unique_new_cycles
        all_cycles.sort(key=lambda c: c.start_time)

        # Use provided retention_days or fall back to instance default
        stored_retention_days = (
            retention_days if retention_days is not None else self._retention_days
        )

        # Update storage
        self._data[device_id] = {
            "cycles": self._serialize_heating_cycles(all_cycles),
            "last_search_time": self._serialize_datetime(search_end_time),
            "retention_days": stored_retention_days,
        }

        await self._save_data()

        _LOGGER.debug(
            "Appended %d unique cycles (total now: %d) for device %s",
            len(unique_new_cycles),
            len(all_cycles),
            device_id,
        )
        _LOGGER.debug("Exiting HAHeatingCycleStorage.append_cycles")

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
        _LOGGER.debug("Entering HAHeatingCycleStorage.prune_old_cycles")
        _LOGGER.debug(
            "Pruning cycles for device_id=%s, reference_time=%s",
            device_id,
            reference_time,
        )

        await self._ensure_loaded()

        cache_data = await self.get_cache_data(device_id)
        if not cache_data:
            _LOGGER.debug("No cache to prune for device %s", device_id)
            _LOGGER.debug("Exiting HAHeatingCycleStorage.prune_old_cycles")
            return

        cutoff_time = reference_time - timedelta(days=cache_data.retention_days)

        # Filter cycles within retention
        retained_cycles = [cycle for cycle in cache_data.cycles if cycle.start_time >= cutoff_time]

        removed_count = len(cache_data.cycles) - len(retained_cycles)

        if removed_count > 0:
            # Update storage
            self._data[device_id] = {
                "cycles": self._serialize_heating_cycles(retained_cycles),
                "last_search_time": self._serialize_datetime(cache_data.last_search_time),
                "retention_days": cache_data.retention_days,
            }

            await self._save_data()

            _LOGGER.debug(
                "Pruned %d cycles older than %s (retained %d)",
                removed_count,
                cutoff_time,
                len(retained_cycles),
            )
        else:
            _LOGGER.debug("No cycles to prune for device %s", device_id)

        _LOGGER.debug("Exiting HAHeatingCycleStorage.prune_old_cycles")

    async def clear_cache(self, device_id: str) -> None:
        """Clear all cached cycles for a device.

        Args:
            device_id: The device identifier
        """
        _LOGGER.debug("Entering HAHeatingCycleStorage.clear_cache")
        _LOGGER.debug("Clearing cache for device_id=%s", device_id)

        await self._ensure_loaded()

        if device_id in self._data:
            del self._data[device_id]
            await self._save_data()
            _LOGGER.debug("Cleared cache for device %s", device_id)
        else:
            _LOGGER.debug("No cache to clear for device %s", device_id)

        _LOGGER.debug("Exiting HAHeatingCycleStorage.clear_cache")

    async def get_last_search_time(self, device_id: str) -> datetime | None:
        """Get the timestamp of the last cycle search.

        Args:
            device_id: The device identifier

        Returns:
            UTC timestamp of last search, or None if no cache exists
        """
        _LOGGER.debug("Entering HAHeatingCycleStorage.get_last_search_time")
        _LOGGER.debug("Getting last search time for device_id=%s", device_id)

        cache_data = await self.get_cache_data(device_id)

        result = cache_data.last_search_time if cache_data else None

        _LOGGER.debug("Last search time for device %s: %s", device_id, result)
        _LOGGER.debug("Exiting HAHeatingCycleStorage.get_last_search_time")

        return result

    def _serialize_heating_cycles(self, cycles: list[HeatingCycle]) -> list[dict[str, Any]]:
        """Serialize HeatingCycle objects to JSON-compatible dicts.

        Args:
            cycles: List of HeatingCycle objects

        Returns:
            List of serialized cycle dictionaries
        """
        return [self._serialize_heating_cycle(cycle) for cycle in cycles]

    def _serialize_heating_cycle(self, cycle: HeatingCycle) -> dict[str, Any]:
        """Serialize a single HeatingCycle to a JSON-compatible dict.

        Args:
            cycle: HeatingCycle object

        Returns:
            Serialized cycle dictionary
        """
        cycle_dict = {
            "device_id": cycle.device_id,
            "start_time": self._serialize_datetime(cycle.start_time),
            "end_time": self._serialize_datetime(cycle.end_time),
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

        return cycle_dict

    def _deserialize_heating_cycles(self, cycle_dicts: list[dict[str, Any]]) -> list[HeatingCycle]:
        """Deserialize JSON-compatible dicts to HeatingCycle objects.

        Args:
            cycle_dicts: List of serialized cycle dictionaries

        Returns:
            List of HeatingCycle objects
        """
        cycles = []
        for cycle_dict in cycle_dicts:
            try:
                cycle = self._deserialize_heating_cycle(cycle_dict)
                cycles.append(cycle)
            except (KeyError, ValueError, TypeError) as exc:
                _LOGGER.warning("Failed to deserialize cycle: %s", exc)
                continue

        return cycles

    def _deserialize_heating_cycle(self, cycle_dict: dict[str, Any]) -> HeatingCycle:
        """Deserialize a single JSON-compatible dict to HeatingCycle object.

        Args:
            cycle_dict: Serialized cycle dictionary

        Returns:
            HeatingCycle object

        Raises:
            KeyError, ValueError, TypeError: If deserialization fails
        """
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

        return HeatingCycle(
            device_id=cycle_dict["device_id"],
            start_time=self._parse_datetime(cycle_dict["start_time"]),
            end_time=self._parse_datetime(cycle_dict["end_time"]),
            target_temp=cycle_dict["target_temp"],
            end_temp=cycle_dict["end_temp"],
            start_temp=cycle_dict["start_temp"],
            tariff_details=tariff_details,
        )
