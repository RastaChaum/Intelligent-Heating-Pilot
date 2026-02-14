"""Calculate Anticipation Use Case.

This use case calculates the anticipated start time for preheating
and optionally schedules the preheating action.

STEP 1 IMPLEMENTATION: This is a facade/wrapper that delegates to
HeatingApplicationService.calculate_and_schedule_anticipation().
No behavior change - pure delegation pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class CalculateAnticipationUseCase:
    """Use case for calculating anticipation and scheduling preheating.

    This use case encapsulates the logic for:
    1. Reading the next scheduled timeslot
    2. Calculating the anticipated start time based on learned heating slope
    3. Optionally scheduling the preheating action

    STEP 1: Delegates to HeatingApplicationService (no logic here yet).
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the use case.

        Args:
            application_service: The application service to delegate to
        """
        _LOGGER.debug("Initializing CalculateAnticipationUseCase")
        self._app_service = application_service

    async def execute(self, ihp_enabled: bool = True) -> dict | None:
        """Execute the calculate anticipation use case.

        Args:
            ihp_enabled: Whether IHP preheating is enabled. When False,
                        calculations continue but scheduler commands are skipped.

        Returns:
            Dict with anticipation data for sensors, or None if not applicable.
            When scheduler is not configured or no timeslot is available,
            returns a dict with clear_values=True to reset sensors to unknown state.
        """
        _LOGGER.debug(
            "Entering CalculateAnticipationUseCase.execute(ihp_enabled=%s)",
            ihp_enabled,
        )

        # STEP 1: Delegate to existing application service method
        result = await self._app_service.calculate_and_schedule_anticipation(
            ihp_enabled=ihp_enabled
        )

        _LOGGER.debug(
            "Exiting CalculateAnticipationUseCase.execute() -> %s",
            "data" if result else "None",
        )
        return result
