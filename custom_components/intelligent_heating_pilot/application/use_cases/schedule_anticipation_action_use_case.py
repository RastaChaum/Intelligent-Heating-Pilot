"""Schedule Anticipation Action Use Case.

This use case schedules the anticipation timer to trigger preheating
at the calculated start time.

STEP 1 IMPLEMENTATION: This is a facade/wrapper that delegates to
HeatingApplicationService._schedule_anticipation().
No behavior change - pure delegation pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from .. import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class ScheduleAnticipationActionUseCase:
    """Use case for scheduling anticipation timer.

    This use case encapsulates the logic for:
    1. Canceling existing anticipation timer
    2. Scheduling new anticipation timer
    3. Managing timer state and callbacks

    STEP 1: Delegates to HeatingApplicationService (no logic here yet).
    """

    def __init__(self, application_service: HeatingApplicationService) -> None:
        """Initialize the use case.

        Args:
            application_service: The application service to delegate to
        """
        _LOGGER.debug("Initializing ScheduleAnticipationActionUseCase")
        self._app_service = application_service

    async def execute(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        lhs: float,
    ) -> None:
        """Execute the schedule anticipation action use case.

        Args:
            anticipated_start: When to trigger the anticipation
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            lhs: Learned heating slope (for logging/tracking)
        """
        _LOGGER.debug(
            "Entering ScheduleAnticipationActionUseCase.execute(anticipated_start=%s, scheduler=%s)",
            anticipated_start.isoformat(),
            scheduler_entity_id,
        )

        # STEP 1: Delegate to existing application service method
        await self._app_service._schedule_anticipation(
            anticipated_start=anticipated_start,
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
            lhs=lhs,
        )

        _LOGGER.debug("Exiting ScheduleAnticipationActionUseCase.execute()")

    async def cancel_anticipation_timer(self) -> None:
        """Cancel any active anticipation timer.

        STEP 1: Delegates to _cancel_anticipation_timer().
        """
        _LOGGER.debug("Entering ScheduleAnticipationActionUseCase.cancel_anticipation_timer()")

        # STEP 1: Delegate to existing application service method
        await self._app_service._cancel_anticipation_timer()

        _LOGGER.debug("Exiting ScheduleAnticipationActionUseCase.cancel_anticipation_timer()")
