"""Schedule Anticipation Action Use Case.

This use case encapsulates the complex logic for scheduling preheating based on
anticipation calculations, including revert logic when conditions change.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...const import DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import ISchedulerCommander, ISchedulerReader, ITimerScheduler

_LOGGER = logging.getLogger(__name__)


class ScheduleAnticipationActionUseCase:
    """Use case for scheduling anticipation actions.

    This use case encapsulates the complex logic for:
    1. Checking scheduler state
    2. Handling revert logic when anticipated start is postponed significantly
    3. Scheduling preheating timers
    4. Triggering immediate preheating when needed
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        scheduler_commander: ISchedulerCommander,
        timer_scheduler: ITimerScheduler,
        control_preheating_use_case,  # ControlPreheatingUseCase (avoid circular import)
        anticipation_recalc_tolerance_minutes: int = DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
        on_scheduler_blocked: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduler state
            scheduler_commander: Triggers scheduler actions
            timer_scheduler: Schedules timer callbacks
            control_preheating_use_case: Use case for managing preheating state
            anticipation_recalc_tolerance_minutes: Min absolute delta in anticipated
                start time required to cancel active preheating and reschedule
            on_scheduler_blocked: Called with the scheduler entity id when a
                timer-fired trigger is confirmed blocked. The immediate-trigger
                path (inside an awaited call) instead returns the blocked id
                directly to its caller; the timer-fired path fires later, with
                no caller left to receive a return value, so it uses this
                callback instead. Optional: when omitted, a timer-fired block
                is still logged, just not retried.
        """
        _LOGGER.debug("Initializing ScheduleAnticipationActionUseCase")
        self._scheduler_reader = scheduler_reader
        self._scheduler_commander = scheduler_commander
        self._timer_scheduler = timer_scheduler
        self._control_preheating = control_preheating_use_case
        self._on_scheduler_blocked = on_scheduler_blocked

        # Scheduling-specific state (not preheating state - delegated to ControlPreheatingUseCase)
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._anticipation_timer_cancel: Callable[[], None] | None = None
        self._preheating_target_temp: float | None = None  # Temp only (time/active delegated)
        self._anticipation_recalc_tolerance_seconds = anticipation_recalc_tolerance_minutes * 60

    def set_on_scheduler_blocked(self, callback: Callable[[str], Awaitable[None]] | None) -> None:
        """Set the callback invoked when a timer-fired trigger is confirmed blocked.

        Wired by the composition root *after* the orchestrator is constructed,
        breaking the circular dependency between this use case (built first)
        and the orchestrator, which owns the retry loop this callback re-enters.

        Args:
            callback: Async callback receiving the blocked scheduler entity id,
                or None to clear it.
        """
        self._on_scheduler_blocked = callback

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
    ) -> str | None:
        """Handle the complete scheduling workflow based on anticipation data and IHP status.

        This method contains all the business logic for deciding when to schedule/cancel
        preheating based on data availability, IHP status, and current state.

        Args:
            anticipation_data: Calculated anticipation data
            ihp_enabled: Whether IHP is enabled

        Returns:
            The scheduler entity id if an immediate trigger was confirmed blocked
            this call (conditions unmet), so the caller can retry excluding it;
            None otherwise (nothing attempted, or the attempt succeeded).
        """
        _LOGGER.debug(
            "Entering handle_anticipation_scheduling(ihp_enabled=%s, has_data=%s)",
            ihp_enabled,
            anticipation_data.get("anticipated_start_time") is not None,
        )

        await self._complete_elapsed_preheating()

        # Decision 1: No valid data - cancel everything
        if anticipation_data.get("anticipated_start_time") is None:
            _LOGGER.debug("No valid anticipation data - cancelling any active scheduling")
            await self.cancel_action()
            await self._control_preheating.cancel_preheating(
                self._control_preheating.get_active_scheduler_entity()
                or anticipation_data.get("scheduler_entity")
            )
            return None

        # Decision 2: IHP disabled - cancel but don't schedule
        if not ihp_enabled:
            _LOGGER.debug("IHP disabled - cancelling preheating if active")
            await self._control_preheating.cancel_preheating(
                self._control_preheating.get_active_scheduler_entity()
                or anticipation_data.get("scheduler_entity")
            )
            await self.cancel_action()
            return None

        await self._cancel_preheating_for_other_slot(anticipation_data["next_schedule_time"])

        # Decision 3: No heating time needed (anticipation_minutes == 0)
        if anticipation_data.get("anticipation_minutes") == 0:
            await self._handle_no_heating_needed(anticipation_data)
            return None

        # Decision 4: No scheduler entity - skip scheduling
        scheduler_entity = anticipation_data.get("scheduler_entity")
        if not scheduler_entity:
            _LOGGER.debug("No scheduler entity - skipping scheduling")
            return None

        # Decision 5: Valid data + IHP enabled + scheduler available - schedule
        return await self.schedule_action(
            anticipated_start=anticipation_data["anticipated_start_time"],
            target_time=anticipation_data["next_schedule_time"],
            target_temp=anticipation_data["next_target_temperature"],
            scheduler_entity_id=scheduler_entity,
            lhs=float(anticipation_data.get("learned_heating_slope") or 0.0),
        )

    async def _cancel_preheating_for_other_slot(self, target_time: datetime) -> None:
        """Revert an active preheat whose slot is no longer the next one.

        The slot was removed or moved, so the scheduler will never apply it and
        _complete_elapsed_preheating() would leave its setpoint on the thermostat.

        Does NOT revert when the active scheduler is still enabled: with the
        earliest-scheduler-first retry added for #64, a fresh recalculation
        always recomputes the "next timeslot" starting from the earliest
        configured scheduler, even while a different scheduler is already
        correctly, actively preheating after an earlier fallback. Reverting
        here on every such tick - before even knowing whether this tick's
        earliest candidate will itself be blocked again - caused a visible
        comfort/eco flap each recalculation cycle. The active scheduler being
        enabled is treated as "still legitimate, leave it running"; only a
        genuinely disabled/removed active scheduler is reverted.

        Args:
            target_time: Target time of the next scheduled slot
        """
        if not self._control_preheating.is_preheating_active():
            return
        preheating_target = self._control_preheating.get_preheating_target_time()
        if preheating_target == target_time:
            return
        active_scheduler = self._control_preheating.get_active_scheduler_entity()
        if active_scheduler and await self._scheduler_reader.is_scheduler_enabled(active_scheduler):
            _LOGGER.debug(
                "Next slot differs (%s vs %s) but active scheduler %s is still "
                "enabled - keeping it running instead of reverting",
                preheating_target,
                target_time.isoformat(),
                active_scheduler,
            )
            return
        _LOGGER.info(
            "Next slot changed from %s to %s - reverting active preheating",
            preheating_target,
            target_time.isoformat(),
        )
        await self._control_preheating.cancel_preheating()
        await self._clear_state()

    async def _handle_no_heating_needed(self, anticipation_data: dict) -> None:
        """Handle a recalculation that reports zero minutes of anticipation.

        Zero minutes means either the temperature is unknown or the room is
        already at target. Neither case must revert an active preheat: the
        next recalculation would restart it and the setpoint would flap
        between comfort and eco until the slot fires.

        Args:
            anticipation_data: Calculated anticipation data
        """
        if anticipation_data.get("current_temp") is None:
            _LOGGER.debug("Indoor temperature unavailable - keeping current preheating state")
            return
        if self._control_preheating.is_preheating_active():
            _LOGGER.debug("Target reached early - keeping active preheating until its slot")
            return
        _LOGGER.debug("Target reached - clearing anticipation state")
        await self.cancel_action()

    async def schedule_action(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        lhs: float,
    ) -> str | None:
        """Schedule heating anticipation action.

        This method handles all the scheduling logic including:
        - Checking scheduler state
        - Handling revert when anticipated time changes significantly
        - Scheduling timers for future starts
        - Triggering immediate preheating if start is in the past

        Args:
            anticipated_start: When to start preheating
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            lhs: Learned heating slope

        Returns:
            ``scheduler_entity_id`` if an immediate trigger was confirmed blocked
            this call, otherwise None.
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
            return None

        # Handle revert logic: cancel active preheating only when anticipated start is pushed later
        # by at least the configured tolerance, and only if the new start is still ahead:
        # a start already in the past would restart preheating on the same tick.
        if self._control_preheating.is_preheating_active():
            preheating_target = self._control_preheating.get_preheating_target_time()
            postponed_seconds = 0.0
            if self._last_scheduled_time is not None:
                postponed_seconds = (anticipated_start - self._last_scheduled_time).total_seconds()
            if (
                preheating_target == target_time
                and self._last_scheduled_time is not None
                and postponed_seconds >= self._anticipation_recalc_tolerance_seconds
                and anticipated_start > now
            ):
                delta_minutes = postponed_seconds / 60.0
                _LOGGER.info(
                    "Anticipated start moved later significantly (delta: %.1f min, "
                    "threshold: %.1f min). Reverting active preheating and rescheduling.",
                    delta_minutes,
                    self._anticipation_recalc_tolerance_seconds / 60.0,
                )

                # Delegate cancellation to ControlPreheatingUseCase
                await self._control_preheating.cancel_preheating(scheduler_entity_id)
            # An elapsed preheat was already completed by _complete_elapsed_preheating()

        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs

        # If anticipated start is in past but target is future, trigger now
        if anticipated_start <= now < target_time:
            blocked_entity: str | None = None
            if not self._control_preheating.is_preheating_active():
                _LOGGER.info(
                    "Anticipated start %s is past, triggering preheating immediately",
                    anticipated_start.isoformat(),
                )
                # A timer left by an earlier calculation would otherwise fire during this preheat
                await self._cancel_timer()
                confirmed = await self._control_preheating.start_preheating(
                    target_time, target_temp, scheduler_entity_id
                )
                if not confirmed:
                    _LOGGER.warning(
                        "Scheduler %s confirmed blocked (conditions unmet)", scheduler_entity_id
                    )
                    blocked_entity = scheduler_entity_id
            else:
                _LOGGER.debug(
                    "Already preheating, continuing through target time %s", target_time.isoformat()
                )
            _LOGGER.debug("Exiting schedule_action() -> immediate trigger")
            return blocked_entity

        # Both times in past - skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are in past, skipping")
            await self._cancel_timer()
            return None

        # Schedule timer for future start only if preheating is not already active.
        if not self._control_preheating.is_preheating_active():
            await self._schedule_timer(
                anticipated_start,
                target_time,
                target_temp,
                scheduler_entity_id,
            )
        _LOGGER.debug("Exiting schedule_action() -> timer scheduled")
        return None

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
            blocked_entity = await self._trigger_action(
                target_time, target_temp, scheduler_entity_id
            )

            # The timer fires outside any caller's awaited call stack, so a
            # confirmed block cannot be returned - it is handed to this
            # callback instead, which the orchestrator wires to its own
            # retry loop (see ScheduleAnticipationActionUseCase.set_on_scheduler_blocked).
            if blocked_entity is not None and self._on_scheduler_blocked is not None:
                await self._on_scheduler_blocked(blocked_entity)

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
    ) -> str | None:
        """Trigger the preheating action via scheduler.

        Args:
            target_time: Target time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity

        Returns:
            ``scheduler_entity_id`` if the action was confirmed blocked
            (conditions unmet), otherwise None.
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
            return None

        # Delegate to ControlPreheatingUseCase
        confirmed = await self._control_preheating.start_preheating(
            target_time, target_temp, scheduler_entity_id
        )
        if not confirmed:
            _LOGGER.warning(
                "Scheduler %s confirmed blocked (conditions unmet)", scheduler_entity_id
            )
            return scheduler_entity_id

        self._preheating_target_temp = target_temp
        _LOGGER.debug("Action triggered successfully")
        return None

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

    async def _complete_elapsed_preheating(self) -> None:
        """Mark active preheating complete once its target slot has fired.

        The next recalculation targets the following slot, so the active flag must
        be cleared here, otherwise it would block scheduling of that next slot.
        """
        if not self._control_preheating.is_preheating_active():
            return
        preheating_target = self._control_preheating.get_preheating_target_time()
        if preheating_target is None or dt_util.now() < preheating_target:
            return
        _LOGGER.info("Preheating target time %s reached, preheating complete", preheating_target)
        self._control_preheating.mark_preheating_complete()
        await self._clear_state()

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
