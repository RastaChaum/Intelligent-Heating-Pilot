"""Reset Learning Data Use Case.

This use case resets all learned data:
- Learned heating slopes (LHS)
- Cached heating cycles

This allows the system to start learning from scratch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.interfaces import IHeatingCycleStorage, ILhsStorage

_LOGGER = logging.getLogger(__name__)


class ResetLearningUseCase:
    """Use case for resetting all learned heating data.

    This use case encapsulates the logic for:
    1. Clearing all learned heating slopes from storage
    2. Clearing all cached heating cycles
    3. Logging the reset operation

    This allows the system to start fresh with no historical learning data.
    """

    def __init__(
        self,
        lhs_storage: ILhsStorage,
        cycle_cache: IHeatingCycleStorage,
    ) -> None:
        """Initialize the use case.

        Args:
            lhs_storage: Storage for learned heating slopes
            cycle_cache: Storage for heating cycle cache
        """
        _LOGGER.debug("Initializing ResetLearningUseCase")
        self._lhs_storage = lhs_storage
        self._cycle_cache = cycle_cache

    async def reset_all_learning_data(self, device_id: str) -> None:
        """Reset all learned data (LHS + heating cycles cache).

        Args:
            device_id: Device identifier
        """
        _LOGGER.debug(
            "Entering ResetLearningUseCase.reset_all_learning_data(device_id=%s)",
            device_id,
        )
        _LOGGER.info("Resetting all learned data (LHS + cycles) for device %s", device_id)

        # Reset learned heating slopes
        await self._lhs_storage.clear_slope_history()
        _LOGGER.info("Learned heating slopes have been reset")

        # Reset heating cycle cache
        await self._cycle_cache.clear_cache(device_id)
        _LOGGER.info("Heating cycle cache has been reset")

        _LOGGER.info("All learning data has been reset for device %s", device_id)
        _LOGGER.debug("Exiting ResetLearningUseCase.reset_all_learning_data()")
