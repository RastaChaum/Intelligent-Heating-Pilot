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

    from ...domain.interfaces import IHeatingCycleStorage, ILhsStorage
    from ...domain.value_objects import HeatingCycle, HeatingCycleCacheData
    from ..lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)


class UpdateCacheDataUseCase:
    """Use case for managing heating cycle cache.

    This use case encapsulates the logic for:
    1. Getting cycles from cache
    2. Updating cache (append new cycles, then prune old ones)
    3. Recalculating LHS when cycles change
    4. Resetting cache completely
    """

    def __init__(
        self,
        cycle_storage: IHeatingCycleStorage,
        lhs_storage: ILhsStorage,
        lhs_lifecycle_manager: LhsLifecycleManager,
    ) -> None:
        """Initialize the use case.

        Args:
            cycle_storage: Heating cycle cache storage
            lhs_storage: LHS storage for clearing
            lhs_lifecycle_manager: Manages LHS recalculation
        """
        _LOGGER.debug("Initializing UpdateCacheDataUseCase")
        self._cycle_storage = cycle_storage
        self._lhs_storage = lhs_storage
        self._lhs_manager = lhs_lifecycle_manager

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

        cache_data = await self._cycle_storage.get_cache_data(device_id)

        _LOGGER.debug(
            "Exiting UpdateCacheDataUseCase.get_cache_data() -> %s",
            "data" if cache_data else "None",
        )
        return cache_data

    async def append_cycles(
        self,
        device_id: str,
        cycles: list[HeatingCycle],
        reference_time: datetime,
    ) -> None:
        """Append new cycles to cache and prune old ones.

        Args:
            device_id: Device identifier
            cycles: New heating cycles to append
            reference_time: Reference time for pruning old cycles
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.append_cycles(device_id=%s, cycles=%d)",
            device_id,
            len(cycles),
        )

        # Append cycles to storage (storage handles deduplication)
        await self._cycle_storage.append_cycles(device_id, cycles, reference_time)

        _LOGGER.info(
            "Appended %d cycles to cache for device %s",
            len(cycles),
            device_id,
        )

        # Prune old cycles based on retention
        await self.prune_old_cycles(device_id, reference_time)

        _LOGGER.debug("Exiting UpdateCacheDataUseCase.append_cycles()")

    async def prune_old_cycles(
        self,
        device_id: str,
        reference_time: datetime,
    ) -> None:
        """Prune cycles older than retention period and recalculate LHS.

        Args:
            device_id: Device identifier
            reference_time: Reference time for retention calculation
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.prune_old_cycles(device_id=%s, reference_time=%s)",
            device_id,
            reference_time.isoformat(),
        )

        # Prune old cycles
        await self._cycle_storage.prune_old_cycles(device_id, reference_time)

        # Recalculate LHS after pruning (cycles have changed)
        await self._lhs_manager.update_global_lhs_from_cache(device_id)
        _LOGGER.info("LHS recalculated after pruning old cycles")

        _LOGGER.debug("Exiting UpdateCacheDataUseCase.prune_old_cycles()")

    async def reset_cache(self, device_id: str) -> None:
        """Reset cache completely for a device (both cycles and LHS).

        This deletes all cached cycles and LHS data.

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.reset_cache(device_id=%s)",
            device_id,
        )
        _LOGGER.info("Resetting heating cycle cache and LHS for device %s", device_id)

        # Clear all cycle cache data
        await self._cycle_storage.clear_cache(device_id)
        _LOGGER.info("Heating cycle cache has been reset")

        # Clear LHS data
        await self._lhs_storage.clear_slopes_datas()
        _LOGGER.info("LHS data has been reset")

        _LOGGER.info("Cache and LHS have been reset for device %s", device_id)
        _LOGGER.debug("Exiting UpdateCacheDataUseCase.reset_cache()")
