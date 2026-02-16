"""Schedule Anticipation Action Use Case.

This use case encapsulates the complex logic for scheduling preheating based on
anticipation calculations, including revert logic when conditions change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import ISchedulerCommander, ISchedulerReader, ITimerScheduler

_LOGGER = logging.getLogger(__name__)


class ScheduleAnticipationActionUseCase:
    """Use case for scheduling anticipation actions.

    This use case encapsulates the complex logic for:
    1. Checking scheduler state
    2. Handling revert logic when LHS improvements occur
    3. Scheduling preheating timers
    4. Triggering immediate preheating when needed
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        scheduler_commander: ISchedulerCommander,
        timer_scheduler: ITimerScheduler,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduler state
            scheduler_commander: Triggers scheduler actions
            timer_scheduler: Schedules timer callbacks
        """
        _LOGGER.debug("Initializing ScheduleAnticipationActionUseCase")
        self._scheduler_reader = scheduler_reader
        self._scheduler_commander = scheduler_commander
        self._timer_scheduler = timer_scheduler

        # State tracking for preheating
        self._is_preheating_active = False
        self._preheating_target_time: datetime | None = None
        self._preheating_target_temp: float | None = None
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._active_scheduler_entity: str | None = None
        self._anticipation_timer_cancel: Callable[[], None] | None = None

    def set_preheating_state(
        self,
        is_active: bool,
        target_time: datetime | None = None,
        target_temp: float | None = None,
    ) -> None:
        """Update preheating tracking state.

        Args:
            is_active: Whether preheating is active
            target_time: Target time for preheating
            target_temp: Target temperature
        """
        _LOGGER.debug(
            "Setting preheating state: active=%s, target_time=%s, target_temp=%.1f",
            is_active,
            target_time.isoformat() if target_time else None,
            target_temp or 0.0,
        )
        self._is_preheating_active = is_active
        self._preheating_target_time = target_time
        self._preheating_target_temp = target_temp

    async def schedule_action(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        lhs: float,
    ) -> None:
        """Schedule heating anticipation action.

        This method handles all the scheduling logic including:
        - Checking scheduler state
        - Handling revert when LHS improves
        - Scheduling timers for future starts
        - Triggering immediate preheating if start is in the past

        Args:
            anticipated_start: When to start preheating
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            lhs: Learned heating slope
        """
        _LOGGER.debug(
            "Entering ScheduleAnticipationActionUseCase.schedule_action("
            "anticipated_start=%s, scheduler=%s)",
            anticipated_start.isoformat(),
            scheduler_entity_id,
        )

        now = dt_util.now()

        # Check if scheduler is enabled
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning(
                "Scheduler %s is disabled. Skipping anticipation scheduling.",
                scheduler_entity_id,
            )
            if self._active_scheduler_entity == scheduler_entity_id:
                await self._clear_state()
            return

        # Track scheduler entity for later disable detection
        if self._active_scheduler_entity != scheduler_entity_id:
            self._active_scheduler_entity = scheduler_entity_id

        # Handle revert logic: if LHS improved, cancel active preheating and reschedule
        if self._is_preheating_active:
            if anticipated_start > now and self._preheating_target_time == target_time:
                _LOGGER.info(
                    "Anticipated start moved later (now: %s, new start: %s). "
                    "LHS improved from %.2f to %.2f°C/h. Reverting and rescheduling.",
                    now.isoformat(),
                    anticipated_start.isoformat(),
                    self._last_scheduled_lhs or 0.0,
                    lhs,
                )

                await self._scheduler_commander.cancel_action(scheduler_entity_id)

                self._last_scheduled_time = anticipated_start
                self._last_scheduled_lhs = lhs
                self._is_preheating_active = False
                self._preheating_target_time = None

                # Schedule timer for new anticipated time
                await self._schedule_timer(
                    anticipated_start,
                    target_time,
                    target_temp,
                    scheduler_entity_id,
                )
                _LOGGER.debug("Exiting schedule_action() -> rescheduled timer")
                return

            # If target time reached, mark complete
            if now >= target_time:
                _LOGGER.info("Target time reached, preheating complete")
                await self._clear_state()
                return

        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs

        # If anticipated start is in past but target is future, trigger now
        if anticipated_start <= now < target_time:
            if not self._is_preheating_active:
                _LOGGER.info(
                    "Anticipated start %s is past, triggering preheating immediately",
                    anticipated_start.isoformat(),
                )
                await self._scheduler_commander.run_action(target_time, scheduler_entity_id)
                self._is_preheating_active = True
                self._preheating_target_time = target_time
                self._active_scheduler_entity = scheduler_entity_id
            else:
                _LOGGER.debug(
                    "Already preheating, continuing through target time %s", target_time.isoformat()
                )
            _LOGGER.debug("Exiting schedule_action() -> immediate trigger")
            return

        # Both times in past - skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are in past, skipping")
            await self._cancel_timer()
            return

        # Schedule timer for future start
        await self._schedule_timer(
            anticipated_start,
            target_time,
            target_temp,
            scheduler_entity_id,
        )
        _LOGGER.debug("Exiting schedule_action() -> timer scheduled")

    async def _schedule_timer(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> None:
        """Schedule a timer to trigger preheating at anticipated start time.

        Args:
            anticipated_start: When timer should fire
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler to trigger
        """
        _LOGGER.debug(
            "Scheduling timer: anticipated_start=%s, scheduler=%s",
            anticipated_start.isoformat(),
            scheduler_entity_id,
        )

        # Cancel existing timer
        await self._cancel_timer()

        # Create callback
        async def _timer_callback() -> None:
            """Execute when timer fires."""
            _LOGGER.info(
                "Anticipation timer fired at %s for target %s (%.1f°C)",
                dt_util.now().isoformat(),
                target_time.isoformat(),
                target_temp,
            )

            # Clear timer reference
            self._anticipation_timer_cancel = None

            # Trigger the action
            await self._trigger_action(target_time, target_temp, scheduler_entity_id)

        # Schedule the timer
        self._anticipation_timer_cancel = self._timer_scheduler.schedule_timer(
            anticipated_start,
            _timer_callback,
        )

        now = dt_util.now()
        wait_minutes = (anticipated_start - now).total_seconds() / 60.0
        _LOGGER.info(
            "Anticipation timer scheduled: will trigger at %s (in %.1f minutes)",
            anticipated_start.isoformat(),
            wait_minutes,
        )

    async def _trigger_action(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> None:
        """Trigger the preheating action via scheduler.

        Args:
            target_time: Target time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity
        """
        _LOGGER.debug(
            "Triggering anticipation action: target_time=%s, temp=%.1f°C",
            target_time.isoformat(),
            target_temp,
        )

        # Verify scheduler is still enabled
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning("Scheduler %s is disabled, cannot trigger action", scheduler_entity_id)
            await self._clear_state()
            return

        # Trigger via scheduler
        await self._scheduler_commander.run_action(target_time, scheduler_entity_id)

        # Mark as active
        self._is_preheating_active = True
        self._preheating_target_time = target_time
        self._active_scheduler_entity = scheduler_entity_id

        _LOGGER.debug("Action triggered successfully")

    async def _cancel_timer(self) -> None:
        """Cancel any active timer."""
        _LOGGER.debug("Entering cancel_timer")
        if self._anticipation_timer_cancel:
            _LOGGER.debug("Canceling active timer")
            self._anticipation_timer_cancel()
            self._anticipation_timer_cancel = None
        _LOGGER.debug("Exiting cancel_timer")

    async def _clear_state(self) -> None:
        """Clear all tracking state."""
        _LOGGER.debug("Clearing anticipation state")
        await self._cancel_timer()
        self._is_preheating_active = False
        self._preheating_target_time = None
        self._preheating_target_temp = None
        self._active_scheduler_entity = None
        self._last_scheduled_time = None
        self._last_scheduled_lhs = None

    def get_preheating_state(self) -> tuple[bool, datetime | None, float | None]:
        """Get current preheating state.

        Returns:
            Tuple of (is_active, target_time, target_temp)
        """
        return (
            self._is_preheating_active,
            self._preheating_target_time,
            self._preheating_target_temp,
        )
