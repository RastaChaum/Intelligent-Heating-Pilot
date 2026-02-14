"""Reset Learning Use Case.

This use case resets all learned heating slopes,
clearing the model storage and cache.

STEP 1 IMPLEMENTATION: This is a facade/wrapper that delegates to
HeatingApplicationService.reset_learned_slopes().
No behavior change - pure delegation pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class ResetLearningUseCase:
    """Use case for resetting learned heating slopes.

    This use case encapsulates the logic for:
    1. Clearing all learned slopes from storage
    2. Resetting the LHS cache
    3. Logging the reset operation

    STEP 1: Delegates to HeatingApplicationService (no logic here yet).
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the use case.

        Args:
            application_service: The application service to delegate to
        """
        _LOGGER.debug("Initializing ResetLearningUseCase")
        self._app_service = application_service

    async def execute(self) -> None:
        """Execute the reset learning use case.

        This clears all learned heating slopes from storage.
        """
        _LOGGER.debug("Entering ResetLearningUseCase.execute()")
        _LOGGER.info("Resetting all learned heating slopes")

        # STEP 1: Delegate to existing application service method
        await self._app_service.reset_learned_slopes()

        _LOGGER.info("Learned heating slopes have been reset")
        _LOGGER.debug("Exiting ResetLearningUseCase.execute()")
