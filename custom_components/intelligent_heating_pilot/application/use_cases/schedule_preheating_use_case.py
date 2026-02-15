"""Schedule Preheating Use Case.

This use case schedules the preheating timer to trigger preheating
at the calculated start time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import ITimerScheduler

_LOGGER = logging.getLogger(__name__)


class SchedulePreheatingUseCase:
    """Use case for scheduling preheating timer.

    This use case encapsulates the logic for:
    1. Canceling existing preheating timer
    2. Scheduling new preheating timer with callback
    3. Managing timer state and callbacks
    """

    def __init__(self, timer_scheduler: ITimerScheduler) -> None:
        """Initialize the use case.

        Args:
            timer_scheduler: Schedules timer callbacks
        """
        _LOGGER.debug("Initializing SchedulePreheatingUseCase")
        self._timer_scheduler = timer_scheduler
        self._timer_cancel_callback: Callable[[], None] | None = None

    async def create_preheating_scheduler(
        self,
        anticipated_start: datetime,
        preheating_callback: Callable[[], None],
    ) -> None:
        """Create preheating scheduler to trigger at anticipated start time.

        Args:
            anticipated_start: When to trigger the preheating
            preheating_callback: Callback function to execute when timer fires
                                (typically start_preheating from ControlPreheatingUseCase)
        """
        _LOGGER.debug(
            "Entering SchedulePreheatingUseCase.create_preheating_scheduler(anticipated_start=%s)",
            anticipated_start.isoformat(),
        )

        # Cancel any existing timer first
        await self.cancel_preheating_scheduler()

        # Schedule the new timer
        self._timer_cancel_callback = self._timer_scheduler.schedule_timer(
            anticipated_start,
            preheating_callback,
        )

        _LOGGER.info(
            "Preheating scheduler created: will trigger at %s",
            anticipated_start.isoformat(),
        )

        _LOGGER.debug("Exiting SchedulePreheatingUseCase.create_preheating_scheduler()")

    async def cancel_preheating_scheduler(self) -> None:
        """Cancel any active preheating scheduler."""
        _LOGGER.debug("Entering SchedulePreheatingUseCase.cancel_preheating_scheduler()")

        if self._timer_cancel_callback:
            _LOGGER.debug("Canceling active preheating scheduler")
            self._timer_cancel_callback()
            self._timer_cancel_callback = None
        else:
            _LOGGER.debug("No active preheating scheduler to cancel")

        _LOGGER.debug("Exiting SchedulePreheatingUseCase.cancel_preheating_scheduler()")
