"""Update Cache Data Use Case.

This use case manages the heating cycle cache:
- Get cache data
- Update/prune cache  
- Reset cache completely
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import IHeatingCycleStorage
    from ...domain.value_objects import HeatingCycle, HeatingCycleCacheData

_LOGGER = logging.getLogger(__name__)


class UpdateCacheDataUseCase:
    """Use case for managing heating cycle cache.

    This use case encapsulates the logic for:
    1. Getting cycles from cache
    2. Updating cache (append new cycles)
    3. Pruning old cycles
    4. Resetting cache completely
    """

    def __init__(self, cycle_cache: IHeatingCycleStorage) -> None:
        """Initialize the use case.

        Args:
            cycle_cache: Heating cycle cache storage
        """
        _LOGGER.debug("Initializing UpdateCacheDataUseCase")
        self._cycle_cache = cycle_cache

    async def get_cache_data(self, device_id: str) -> HeatingCycleCacheData | None:
        """Get cache data for a device.

        Args:
            device_id: Device identifier

        Returns:
            Cache data if exists, None otherwise
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.get_cache_data(device_id=%s)",
            device_id,
        )

        cache_data = await self._cycle_cache.get_cache_data(device_id)

        _LOGGER.debug(
            "Exiting UpdateCacheDataUseCase.get_cache_data() -> %s",
            "data" if cache_data else "None",
        )
        return cache_data

    async def append_cycles(
        self,
        device_id: str,
        cycles: list[HeatingCycle],
        search_end_time: datetime,
    ) -> None:
        """Append new cycles to cache.

        Args:
            device_id: Device identifier
            cycles: New heating cycles to append
            search_end_time: End time of the search period
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.append_cycles(device_id=%s, cycles=%d)",
            device_id,
            len(cycles),
        )

        await self._cycle_cache.append_cycles(device_id, cycles, search_end_time)

        _LOGGER.info(
            "Appended %d cycles to cache for device %s",
            len(cycles),
            device_id,
        )
        _LOGGER.debug("Exiting UpdateCacheDataUseCase.append_cycles()")

    async def prune_old_cycles(
        self,
        device_id: str,
        reference_time: datetime,
    ) -> None:
        """Prune cycles older than retention period.

        Args:
            device_id: Device identifier
            reference_time: Reference time for retention calculation
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.prune_old_cycles(device_id=%s, reference_time=%s)",
            device_id,
            reference_time.isoformat(),
        )

        await self._cycle_cache.prune_old_cycles(device_id, reference_time)

        _LOGGER.debug("Exiting UpdateCacheDataUseCase.prune_old_cycles()")

    async def reset_cache(self, device_id: str) -> None:
        """Reset cache completely for a device.

        This deletes all cached cycles.

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.reset_cache(device_id=%s)",
            device_id,
        )
        _LOGGER.info("Resetting heating cycle cache for device %s", device_id)

        # Clear all cache data
        await self._cycle_cache.clear_cache(device_id)

        _LOGGER.info("Heating cycle cache has been reset for device %s", device_id)
        _LOGGER.debug("Exiting UpdateCacheDataUseCase.reset_cache()")
