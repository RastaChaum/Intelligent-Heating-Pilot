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
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from ...domain.interfaces import IHeatingCycleStorage, ILhsStorage
    from ...domain.value_objects import HeatingCycle, HeatingCycleCacheData
    from ..heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager
    from ..lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)


class LearningResetError(RuntimeError):
    """Raised when some learned data could not be cleared during a reset.

    The other steps of the reset have still run; ``failed_steps`` names the
    data that is still stored.
    """

    def __init__(self, failed_steps: list[str]) -> None:
        """Initialize the error.

        Args:
            failed_steps: Names of the learned data that could not be cleared
        """
        super().__init__(f"Could not reset: {', '.join(failed_steps)}")
        self.failed_steps = failed_steps


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
        heating_cycle_manager: HeatingCycleLifecycleManager,
    ) -> None:
        """Initialize the use case.

        Args:
            cycle_storage: Heating cycle cache storage
            lhs_storage: LHS storage for clearing
            lhs_lifecycle_manager: Manages LHS recalculation
            heating_cycle_manager: Manages cycles (its memory cache is cleared on reset)
        """
        _LOGGER.debug("Initializing UpdateCacheDataUseCase")
        self._cycle_storage = cycle_storage
        self._lhs_storage = lhs_storage
        self._lhs_manager = lhs_lifecycle_manager
        self._heating_cycle_manager = heating_cycle_manager

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

        # Note: LHS is automatically updated when cycles change via event listeners
        # No need to explicitly recalculate here
        _LOGGER.info("Old cycles pruned, LHS will be recalculated automatically")

        _LOGGER.debug("Exiting UpdateCacheDataUseCase.prune_old_cycles()")

    async def reset_cache(self, device_id: str) -> None:
        """Reset cache completely for a device (cycles, LHS and dead time).

        This deletes all cached cycles, LHS data and the learned dead time,
        in storage AND in the lifecycle managers' memory caches. The memory
        caches are read before storage, so clearing storage alone would leave
        the old learned values in use until the next restart.

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.reset_cache(device_id=%s)",
            device_id,
        )
        _LOGGER.info("Resetting heating cycle cache and LHS for device %s", device_id)

        # Stop extraction first: a running queue would write learned data back
        # right after the storage below is cleared.
        await self._heating_cycle_manager.cancel_extraction()

        # Every step runs even if an earlier one failed, so a single storage
        # error does not leave the other learned data in place.
        steps: tuple[tuple[str, Callable[[], Awaitable[None]]], ...] = (
            ("heating cycles", lambda: self._reset_cycles(device_id)),
            ("LHS", self._reset_lhs),
            ("learned dead time", lambda: self._lhs_storage.set_learned_dead_time(None)),
        )
        failed_steps: list[str] = []
        # A refresh that already read the cycles finishes first, so its learned
        # values are cleared below instead of being written back afterwards (#225).
        async with self._heating_cycle_manager.learning_lock:
            for name, step in steps:
                try:
                    await step()
                    _LOGGER.info("%s reset for device %s", name.capitalize(), device_id)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("Failed to reset %s for device %s: %s", name, device_id, exc)
                    failed_steps.append(name)

        if failed_steps:
            raise LearningResetError(failed_steps)

        _LOGGER.info("Cache and LHS have been reset for device %s", device_id)
        _LOGGER.debug("Exiting UpdateCacheDataUseCase.reset_cache()")

    async def _reset_cycles(self, device_id: str) -> None:
        """Clear stored cycles, then the memory cache that would mask the change."""
        try:
            await self._cycle_storage.clear_cache(device_id)
        finally:
            self._heating_cycle_manager.invalidate_memory_cache()

    async def _reset_lhs(self) -> None:
        """Clear stored LHS, then the memory cache that would mask the change."""
        try:
            await self._lhs_storage.clear_slope_history()
        finally:
            self._lhs_manager.invalidate_memory_cache()
