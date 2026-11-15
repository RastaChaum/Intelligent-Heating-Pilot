"""Schedule Anticipation Action Use Case.

This use case encapsulates the complex logic for scheduling preheating based on
anticipation calculations, including revert logic when conditions change.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...const import DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES
from ...domain.constants import DEADLINE_RECALC_DELAY_SECONDS, SLOT_DAY_RETRY_DELAY_SECONDS
from ...domain.value_objects import CancelReason, ScheduledTimeslot

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import ISchedulerReader, ITimerScheduler
    from ...domain.value_objects import SlotAction

_LOGGER = logging.getLogger(__name__)


class ScheduleAnticipationActionUseCase:
    """Use case for scheduling anticipation actions.

    This use case encapsulates the complex logic for:
    1. Checking scheduler state
    2. Handling revert logic when anticipated start is postponed significantly
    3. Scheduling preheating timers
    4. Triggering immediate preheating when needed
    5. Retrying on the slot's day a trigger made the day before without effect (#250)
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        timer_scheduler: ITimerScheduler,
        control_preheating_use_case,  # ControlPreheatingUseCase (avoid circular import)
        anticipation_recalc_tolerance_minutes: int = DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
        on_scheduler_blocked: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            scheduler_reader: Reads scheduler state
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
        self._timer_scheduler = timer_scheduler
        self._control_preheating = control_preheating_use_case
        self._on_scheduler_blocked = on_scheduler_blocked

        # Scheduling-specific state (not preheating state - delegated to ControlPreheatingUseCase)
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._anticipation_timer_cancel: Callable[[], None] | None = None
        self._preheating_target_temp: float | None = None  # Temp only (time/active delegated)
        # (target_time, scheduler) of the retry planned for the slot's day, if any (#250)
        self._slot_day_retry: tuple[datetime, str] | None = None
        self._anticipation_recalc_tolerance_seconds = anticipation_recalc_tolerance_minutes * 60
        # The hold of a reached wake-up slot: the slot and the cancel of the timer that ends it
        self._hold_slot: ScheduledTimeslot | None = None
        self._hold_timer_cancel: Callable[[], None] | None = None
        self._control_preheating.set_on_hold_recovered(self._arm_hold_timer)
        # A wake-up source may not change at its deadline: a timer asks for the recalculation
        # that completes the preheat and starts its hold
        self._on_deadline: Callable[[], Awaitable[None]] | None = None
        self._deadline_timer_cancel: Callable[[], None] | None = None
        self._deadline_timer_for: datetime | None = None

    async def next_timeslot_of(self, scheduler_entity_id: str) -> ScheduledTimeslot | None:
        """Give the next timeslot of one scheduler, to reconcile a preheat after a restart.

        Args:
            scheduler_entity_id: The scheduler entity.

        Returns:
            Its next timeslot, or None when it has none or cannot be read.
        """
        return await self._scheduler_reader.get_next_timeslot_of(scheduler_entity_id)

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

    def set_on_deadline(self, callback: Callable[[], Awaitable[None]] | None) -> None:
        """Set the callback that recalculates when a wake-up preheat reaches its deadline.

        Args:
            callback: Async callback, or None to clear it.
        """
        self._on_deadline = callback

    async def handle_anticipation_scheduling(
        self,
        anticipation_data: dict,
        ihp_enabled: bool,
    ) -> str | None:
        """Handle the scheduling workflow, then make sure a wake-up deadline will be noticed.

        See ``_handle_anticipation_scheduling`` for the workflow and what is returned.
        """
        blocked = await self._handle_anticipation_scheduling(anticipation_data, ihp_enabled)
        self._ensure_deadline_timer()
        return blocked

    def _ensure_deadline_timer(self) -> None:
        """Arm one timer at the deadline of an active wake-up preheat, none otherwise."""
        slot = self._control_preheating.get_active_timeslot()
        target = (
            self._control_preheating.get_preheating_target_time()
            if self._control_preheating.is_preheating_active()
            else None
        )
        wanted = (
            target
            if slot is not None
            and target is not None
            and self._on_deadline is not None
            and self._scheduler_reader.is_wake_up_source(slot.scheduler_entity)
            else None
        )
        if wanted == self._deadline_timer_for:
            return
        if self._deadline_timer_cancel is not None:
            self._deadline_timer_cancel()
            self._deadline_timer_cancel = None
        self._deadline_timer_for = wanted
        if wanted is None or self._on_deadline is None:
            return
        callback = self._on_deadline

        async def _deadline_callback() -> None:
            self._deadline_timer_cancel = None
            self._deadline_timer_for = None
            await callback()

        self._deadline_timer_cancel = self._timer_scheduler.schedule_timer(
            wanted + timedelta(seconds=DEADLINE_RECALC_DELAY_SECONDS), _deadline_callback
        )

    async def _handle_anticipation_scheduling(
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
                or anticipation_data.get("scheduler_entity"),
                CancelReason.IHP_DISABLED,
            )
            await self.end_pending_hold()
            await self.cancel_action()
            return None

        await self._cancel_preheating_for_other_slot(
            anticipation_data["next_schedule_time"], self._slot_of(anticipation_data)
        )

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
            action=anticipation_data.get("next_slot_action"),
            slot=self._slot_of(anticipation_data),
        )

    @staticmethod
    def _slot_of(anticipation_data: dict) -> ScheduledTimeslot | None:
        """Give the slot the reader described, so that its identity and hold are kept."""
        slot = anticipation_data.get("next_slot")
        return slot if isinstance(slot, ScheduledTimeslot) else None

    async def _cancel_preheating_for_other_slot(
        self, target_time: datetime, new_slot: ScheduledTimeslot | None = None
    ) -> None:
        """Revert an active preheat whose slot its scheduler no longer has as its next one.

        The slot was removed or moved, so the scheduler will never apply it and
        _complete_elapsed_preheating() would leave its setpoint on the thermostat.

        The preheated slot is compared with the active scheduler's OWN next slot, not with the
        earliest slot of all schedulers. A fresh recalculation always recomputes the "next
        timeslot" starting from the earliest configured scheduler, even while a different
        scheduler is already correctly, actively preheating after an earlier fallback (#64);
        reverting on every such tick caused a visible comfort/eco flap each cycle. Looking at
        the active scheduler alone keeps that preheat running, and still reverts one whose slot
        was moved or removed (an enabled scheduler is no proof that its slot is still there).

        A preheat that involves a wake-up source is the exception: its deadline moves (a snooze),
        a closer one appears, or it vanishes. The first two are handed over, with no restore in
        between; a vanished one is reverted like any removed slot.

        Args:
            target_time: Target time of the next scheduled slot
            new_slot: The next slot as the reader described it, when it did
        """
        if not self._control_preheating.is_preheating_active():
            return
        preheating_target = self._control_preheating.get_preheating_target_time()
        if preheating_target == target_time:
            return
        active_scheduler = self._control_preheating.get_active_scheduler_entity()
        # A wake-up deadline hands the preheat over before the #64 rule can keep the old one
        # running: that rule would leave a closer deadline's own target unapplied.
        if await self._try_hand_over(preheating_target, active_scheduler, new_slot):
            return
        if active_scheduler:
            own_next = await self._scheduler_reader.get_next_timeslot_of(active_scheduler)
            if own_next is not None and own_next.target_time == preheating_target:
                _LOGGER.debug(
                    "Next slot differs (%s vs %s) but %s still has the preheated slot as its "
                    "next one - keeping it running instead of reverting",
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

    async def _try_hand_over(
        self,
        preheating_target: datetime | None,
        active_scheduler: str | None,
        new_slot: ScheduledTimeslot | None,
    ) -> bool:
        """Carry a preheat over to another deadline when a wake-up source is involved.

        A closer deadline always takes over; the same source moved later does too, as long as
        it moves by less than the revert tolerance (a snooze), which is the same line the
        postponed-start revert already draws. A source that no longer has a deadline does not:
        its preheat is for nothing and is reverted.

        Returns:
            True when the preheat was handed over and must not be reverted.
        """
        if new_slot is None or preheating_target is None:
            return False
        reader = self._scheduler_reader
        new_is_source = reader.is_wake_up_source(new_slot.scheduler_entity)
        active_is_source = bool(active_scheduler) and reader.is_wake_up_source(
            active_scheduler or ""
        )
        if not (new_is_source or active_is_source):
            return False
        if active_is_source and await reader.get_next_timeslot_of(active_scheduler or "") is None:
            return False
        shift = (new_slot.target_time - preheating_target).total_seconds()
        same_source = new_is_source and active_scheduler == new_slot.scheduler_entity
        if shift >= 0 and not (same_source and shift < self._anticipation_recalc_tolerance_seconds):
            return False
        _LOGGER.info(
            "Wake-up deadline moved from %s to %s - handing the preheat over instead of reverting",
            preheating_target.isoformat(),
            new_slot.target_time.isoformat(),
        )
        await self._control_preheating.hand_over(new_slot)
        await self._clear_state()
        return True

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
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
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
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent

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
                await self._control_preheating.cancel_preheating(
                    scheduler_entity_id, CancelReason.POSTPONED
                )
            # An elapsed preheat was already completed by _complete_elapsed_preheating()

        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs

        # If anticipated start is in past but target is future, trigger now
        if anticipated_start <= now < target_time:
            blocked_entity: str | None = None
            if self._is_slot_day_retry_pending(target_time, scheduler_entity_id):
                _LOGGER.debug(
                    "Retry of %s already planned on the day of the %s slot - not triggering again",
                    scheduler_entity_id,
                    target_time.isoformat(),
                )
            elif not self._control_preheating.is_preheating_active():
                _LOGGER.info(
                    "Anticipated start %s is past, triggering preheating immediately",
                    anticipated_start.isoformat(),
                )
                # A timer left by an earlier calculation would otherwise fire during this preheat
                await self._cancel_timer()
                confirmed = await self._control_preheating.start_preheating(
                    target_time, target_temp, scheduler_entity_id, action=action, slot=slot
                )
                if not confirmed:
                    blocked_entity = await self._handle_unconfirmed_trigger(
                        now, target_time, target_temp, scheduler_entity_id, action=action, slot=slot
                    )
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
                action=action,
                slot=slot,
            )
        _LOGGER.debug("Exiting schedule_action() -> timer scheduled")
        return None

    async def _schedule_timer(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
    ) -> None:
        """Schedule a timer to trigger preheating at anticipated start time.

        Args:
            anticipated_start: When timer should fire
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler to trigger
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent
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
            self._slot_day_retry = None

            # Trigger the action
            blocked_entity = await self._trigger_action(
                target_time, target_temp, scheduler_entity_id, action=action, slot=slot
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
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
    ) -> str | None:
        """Trigger the preheating action via scheduler.

        Args:
            target_time: Target time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent

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
            target_time, target_temp, scheduler_entity_id, action=action, slot=slot
        )
        if not confirmed:
            return await self._handle_unconfirmed_trigger(
                dt_util.now(),
                target_time,
                target_temp,
                scheduler_entity_id,
                action=action,
                slot=slot,
            )

        self._preheating_target_temp = target_temp
        _LOGGER.debug("Action triggered successfully")
        return None

    async def _handle_unconfirmed_trigger(
        self,
        now: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
    ) -> str | None:
        """Decide what a trigger without effect means: blocked, or too early.

        HACS Scheduler's ``run_action`` looks for the timeslot at the given
        time on the day it is called, not on the slot's day. The day before
        the slot, a schedule that does not run today (Mon-Fri on a Sunday)
        finds no timeslot and does nothing, which says nothing about its own
        conditions: the same scheduler is retried once the slot's day has
        started (#250). On the slot's day, no effect means its conditions
        block it, and the caller falls back to the next scheduler.

        Args:
            now: When the trigger was made
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler that was triggered
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent

        Returns:
            ``scheduler_entity_id`` if the scheduler is confirmed blocked,
            None if a retry was planned on the slot's day instead.
        """
        if await self._retry_on_slot_day(
            now, target_time, target_temp, scheduler_entity_id, action=action, slot=slot
        ):
            return None
        _LOGGER.warning("Scheduler %s confirmed blocked (conditions unmet)", scheduler_entity_id)
        return scheduler_entity_id

    async def _retry_on_slot_day(
        self,
        now: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
    ) -> bool:
        """Plan a retry just after the slot's local midnight, if the slot is on a later day.

        Days are compared in HA's local time zone, the one scheduler-component
        uses for "today". The retry never fires after the slot itself.

        Args:
            now: When the trigger without effect was made
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler to retry
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent

        Returns:
            True if a retry was planned, False if the slot is on today's date.
        """
        slot_day = dt_util.as_local(target_time).date()
        if dt_util.as_local(now).date() >= slot_day:
            return False
        retry_at = min(
            dt_util.start_of_local_day(slot_day) + timedelta(seconds=SLOT_DAY_RETRY_DELAY_SECONDS),
            target_time,
        )
        _LOGGER.info(
            "Scheduler %s had no timeslot to run the day before its %s slot "
            "(HACS Scheduler matches the slot time against the current day) - "
            "retrying at %s instead of falling back to another scheduler",
            scheduler_entity_id,
            target_time.isoformat(),
            retry_at.isoformat(),
        )
        await self._schedule_timer(
            retry_at, target_time, target_temp, scheduler_entity_id, action=action, slot=slot
        )
        self._slot_day_retry = (target_time, scheduler_entity_id)
        return True

    def _is_slot_day_retry_pending(self, target_time: datetime, scheduler_entity_id: str) -> bool:
        """Return True if a retry is already planned on this slot's day for this scheduler.

        Triggering again before midnight would have no effect either, and
        would wait for the thermostat for nothing on every recalculation.

        Args:
            target_time: Target schedule time
            scheduler_entity_id: Scheduler entity

        Returns:
            True if the pending timer is that retry.
        """
        return self._anticipation_timer_cancel is not None and self._slot_day_retry == (
            target_time,
            scheduler_entity_id,
        )

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
        self._slot_day_retry = None
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
        timeslot = self._control_preheating.get_active_timeslot()
        if timeslot is not None and timeslot.hold is not None:
            await self._complete_into_hold(timeslot)
        else:
            await self._control_preheating.mark_preheating_complete()
        await self._clear_state()

    async def _complete_into_hold(self, timeslot: ScheduledTimeslot) -> None:
        """Complete the preheat of a wake-up slot and keep its record until its hold ends.

        The hold lasts as long as the source says, but a scheduler of the same IHP that is
        due before then owns the setting from its slot on: the hold stops there and nothing is
        restored, even if that scheduler applies the very action IHP applied.
        """
        assert timeslot.hold is not None
        nominal_end = timeslot.target_time + timeslot.hold
        scheduler_slot = await self._scheduler_reader.get_next_scheduler_timeslot()
        handoff = scheduler_slot is not None and scheduler_slot.target_time <= nominal_end
        hold_until = scheduler_slot.target_time if handoff and scheduler_slot else nominal_end
        await self._control_preheating.mark_preheating_complete(hold_until, handoff)
        await self._arm_hold_timer(timeslot, hold_until)

    async def _arm_hold_timer(self, timeslot: ScheduledTimeslot, hold_until: datetime) -> None:
        """End a hold at its time: at once when that time has already come."""
        self._cancel_hold_timer()
        if hold_until <= dt_util.now():
            await self._control_preheating.end_hold(timeslot)
            return
        self._hold_slot = timeslot

        async def _hold_timer_callback() -> None:
            self._hold_timer_cancel = None
            self._hold_slot = None
            _LOGGER.info("Hold of %s ended", timeslot.timeslot_id)
            await self._control_preheating.end_hold(timeslot)

        self._hold_timer_cancel = self._timer_scheduler.schedule_timer(
            hold_until, _hold_timer_callback
        )
        _LOGGER.info(
            "Hold of %s keeps the target until %s",
            timeslot.timeslot_id,
            hold_until.isoformat(),
        )

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer_cancel is not None:
            self._hold_timer_cancel()
            self._hold_timer_cancel = None
        self._hold_slot = None

    async def end_pending_hold(self) -> None:
        """End a running hold now, as a cancellation: the earlier state is put back where safe."""
        slot = self._hold_slot
        self._cancel_hold_timer()
        if slot is not None:
            _LOGGER.info("Hold of %s ended early", slot.timeslot_id)
            await self._control_preheating.end_hold(slot)

    def cancel_pending_timers(self) -> None:
        """Drop the hold timer without touching the thermostat (unload or reload).

        The record stays: the reloaded instance finds the hold again and re-arms its timer.
        """
        self._cancel_hold_timer()
        if self._deadline_timer_cancel is not None:
            self._deadline_timer_cancel()
            self._deadline_timer_cancel = None
            self._deadline_timer_for = None

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
