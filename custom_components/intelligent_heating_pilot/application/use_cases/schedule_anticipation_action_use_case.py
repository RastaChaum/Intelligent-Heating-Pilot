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
        control_preheating_use_case,  # ControlPreheatingUseCase (avoid circular import)
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduler state
            scheduler_commander: Triggers scheduler actions
            timer_scheduler: Schedules timer callbacks
            control_preheating_use_case: Use case for managing preheating state
        """
        _LOGGER.debug("Initializing ScheduleAnticipationActionUseCase")
        self._scheduler_reader = scheduler_reader
        self._scheduler_commander = scheduler_commander
        self._timer_scheduler = timer_scheduler
        self._control_preheating = control_preheating_use_case

        # Scheduling-specific state (not preheating state - delegated to ControlPreheatingUseCase)
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._anticipation_timer_cancel: Callable[[], None] | None = None
        self._preheating_target_temp: float | None = None  # Temp only (time/active delegated)

    def set_preheating_temp(self, target_temp: float | None) -> None:
        """Update preheating target temperature.

        Note: Preheating state (active, target_time) is managed by ControlPreheatingUseCase.

        Args:
            target_temp: Target temperature
        """
        _LOGGER.debug("Setting preheating target temp: %.1f", target_temp or 0.0)
        self._preheating_target_temp = target_temp

    async def handle_anticipation_scheduling(
        self,
        anticipation_data: dict,
        ihp_enabled: bool,
    ) -> None:
        """Handle the complete scheduling workflow based on anticipation data and IHP status.

        This method contains all the business logic for deciding when to schedule/cancel
        preheating based on data availability, IHP status, and current state.

        Args:
            anticipation_data: Calculated anticipation data
            ihp_enabled: Whether IHP is enabled
        """
        _LOGGER.debug(
            "Entering handle_anticipation_scheduling(ihp_enabled=%s, has_data=%s)",
            ihp_enabled,
            anticipation_data.get("anticipated_start_time") is not None,
        )

        # Decision 1: No valid data - cancel everything
        if anticipation_data.get("anticipated_start_time") is None:
            _LOGGER.debug("No valid anticipation data - cancelling any active scheduling")
            await self.cancel_action()
            await self._control_preheating.cancel_preheating(
                self._control_preheating.get_active_scheduler_entity()
                or anticipation_data.get("scheduler_entity")
            )
            return

        # Decision 2: IHP disabled - cancel but don't schedule
        if not ihp_enabled:
            _LOGGER.debug("IHP disabled - cancelling preheating if active")
            await self._control_preheating.cancel_preheating(
                self._control_preheating.get_active_scheduler_entity()
                or anticipation_data.get("scheduler_entity")
            )
            await self.cancel_action()
            return

        # Decision 3: Target already reached (anticipation_minutes == 0) - clear state
        if anticipation_data.get("anticipation_minutes") == 0:
            _LOGGER.debug("Target reached - clearing anticipation state")
            await self.cancel_action()
            await self._control_preheating.cancel_preheating(
                self._control_preheating.get_active_scheduler_entity()
                or anticipation_data.get("scheduler_entity")
            )
            return

        # Decision 4: No scheduler entity - skip scheduling
        scheduler_entity = anticipation_data.get("scheduler_entity")
        if not scheduler_entity:
            _LOGGER.debug("No scheduler entity - skipping scheduling")
            return

        # Decision 5: Valid data + IHP enabled + scheduler available - schedule
        await self.schedule_action(
            anticipated_start=anticipation_data["anticipated_start_time"],
            target_time=anticipation_data["next_schedule_time"],
            target_temp=anticipation_data["next_target_temperature"],
            scheduler_entity_id=scheduler_entity,
            lhs=float(anticipation_data.get("learned_heating_slope") or 0.0),
        )

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
            active_scheduler = self._control_preheating.get_active_scheduler_entity()
            if active_scheduler == scheduler_entity_id:
                await self._clear_state()
            return

        # Handle revert logic: if LHS improved, cancel active preheating and reschedule
        if self._control_preheating.is_preheating_active():
            preheating_target = self._control_preheating.get_preheating_target_time()
            if anticipated_start > now and preheating_target == target_time:
                _LOGGER.info(
                    "Anticipated start moved later (now: %s, new start: %s). "
                    "LHS improved from %.2f to %.2f°C/h. Reverting and rescheduling.",
                    now.isoformat(),
                    anticipated_start.isoformat(),
                    self._last_scheduled_lhs or 0.0,
                    lhs,
                )

                # Delegate cancellation to ControlPreheatingUseCase
                await self._control_preheating.cancel_preheating(scheduler_entity_id)

                self._last_scheduled_time = anticipated_start
                self._last_scheduled_lhs = lhs

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
            if not self._control_preheating.is_preheating_active():
                _LOGGER.info(
                    "Anticipated start %s is past, triggering preheating immediately",
                    anticipated_start.isoformat(),
                )
                # Delegate to ControlPreheatingUseCase
                await self._control_preheating.start_preheating(
                    target_time, target_temp, scheduler_entity_id
                )
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

        # Delegate to ControlPreheatingUseCase
        await self._control_preheating.start_preheating(
            target_time, target_temp, scheduler_entity_id
        )
        self._preheating_target_temp = target_temp

        _LOGGER.debug("Action triggered successfully")

    async def _cancel_timer(self) -> None:
        """Cancel any active timer.

        Note: Does NOT clear _preheating_target_time - that's preserved for state tracking.
        """
        _LOGGER.debug("Entering cancel_timer")
        if self._anticipation_timer_cancel:
            _LOGGER.debug("Canceling active timer")
            self._anticipation_timer_cancel()
            self._anticipation_timer_cancel = None
            # Note: Timer cancelled but target_time preserved (as per review feedback)
        _LOGGER.debug("Exiting cancel_timer")

    async def _clear_state(self) -> None:
        """Clear all tracking state."""
        _LOGGER.debug("Clearing anticipation state")
        await self._cancel_timer()
        # Clear scheduling-specific state
        self._preheating_target_temp = None
        self._last_scheduled_time = None
        self._last_scheduled_lhs = None
        # Note: Preheating active/target_time managed by ControlPreheatingUseCase

    async def cancel_action(self) -> None:
        """Cancel any active timer and clear state.

        Called by orchestrator when disabling preheating or when conditions change.
        """
        _LOGGER.debug("Canceling anticipation action")
        await self._cancel_timer()

    def get_preheating_state(self) -> tuple[bool, datetime | None, float | None]:
        """Get current preheating state.

        Delegates to ControlPreheatingUseCase for state queries.

        Returns:
            Tuple of (is_active, target_time, target_temp)
        """
        return (
            self._control_preheating.is_preheating_active(),
            self._control_preheating.get_preheating_target_time(),
            self._preheating_target_temp,
        )
