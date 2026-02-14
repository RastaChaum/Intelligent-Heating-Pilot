"""Update Cache Data Use Case.

This use case updates the heating cycle cache with new data,
implementing incremental cache updates and retention management.

STEP 1 IMPLEMENTATION: This is a facade/wrapper that delegates to
HeatingApplicationService cache management methods.
No behavior change - pure delegation pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.value_objects import HeatingCycle
    from .. import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class UpdateCacheDataUseCase:
    """Use case for updating heating cycle cache.

    This use case encapsulates the logic for:
    1. Getting cycles from cache
    2. Extracting new cycles from recorder
    3. Appending cycles to cache
    4. Pruning old cycles

    STEP 1: Delegates to HeatingApplicationService (no logic here yet).
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the use case.

        Args:
            application_service: The application service to delegate to
        """
        _LOGGER.debug("Initializing UpdateCacheDataUseCase")
        self._app_service = application_service

    async def get_cycles_with_cache(
        self,
        device_id: str,
        target_time: datetime,
    ) -> list[HeatingCycle]:
        """Get heating cycles using cache with incremental updates.

        Args:
            device_id: Device identifier
            target_time: Current target time

        Returns:
            List of heating cycles within retention period

        STEP 1: Delegates to _get_cycles_with_cache().
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.get_cycles_with_cache(device_id=%s, target_time=%s)",
            device_id,
            target_time.isoformat(),
        )

        # STEP 1: Delegate to existing application service method
        cycles = await self._app_service._get_cycles_with_cache(
            device_id=device_id,
            target_time=target_time,
        )

        _LOGGER.debug(
            "Exiting UpdateCacheDataUseCase.get_cycles_with_cache() -> %d cycles",
            len(cycles),
        )
        return cycles

    async def extract_cycles_from_recorder(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract heating cycles directly from Home Assistant recorder.

        Args:
            device_id: Device identifier
            start_time: Start of search period
            end_time: End of search period

        Returns:
            List of extracted heating cycles

        STEP 1: Delegates to _extract_cycles_from_recorder().
        """
        _LOGGER.debug(
            "Entering UpdateCacheDataUseCase.extract_cycles_from_recorder(device_id=%s, start=%s, end=%s)",
            device_id,
            start_time.isoformat(),
            end_time.isoformat(),
        )

        # STEP 1: Delegate to existing application service method
        cycles = await self._app_service._extract_cycles_from_recorder(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
        )

        _LOGGER.debug(
            "Exiting UpdateCacheDataUseCase.extract_cycles_from_recorder() -> %d cycles",
            len(cycles),
        )
        return cycles
