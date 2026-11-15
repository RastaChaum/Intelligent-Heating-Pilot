"""Control Preheating Use Case.

This use case controls the preheating state (start/cancel).
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING

from ...domain.constants import ACTION_EFFECT_TIMEOUT_SECONDS, TARGET_TEMP_MATCH_TOLERANCE_C
from ...domain.value_objects import (
    ActuationResult,
    CancelReason,
    RecoveryOutcome,
    ScheduledTimeslot,
    SlotAction,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from ...domain.interfaces import IClimateDataReader, IPreheatActuator
    from ...domain.interfaces.preheat_actuator_interface import NextTimeslotOf

_LOGGER = logging.getLogger(__name__)

# Results of a direct command that left the climate as it was: nothing is marked active and the
# next recalculation tries again, with no other scheduler tried.
_RETRY_RESULTS = frozenset({ActuationResult.NOT_APPLIED, ActuationResult.SKIPPED})


class ControlPreheatingUseCase:
    """Use case for controlling preheating state.

    This use case encapsulates operations for:
    1. Starting preheating (trigger scheduler action)
    2. Canceling preheating (revert to current scheduled state)
    3. Tracking preheating state
    """

    def __init__(
        self,
        preheat_actuator: IPreheatActuator,
        climate_data_reader: IClimateDataReader | None = None,
        action_effect_timeout_seconds: float = ACTION_EFFECT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the use case.

        Args:
            preheat_actuator: Starts and cancels the preheat of a slot
            climate_data_reader: Reads the VTherm's resulting target temperature
                to verify a triggered action's effect. Optional: when omitted,
                verification is skipped and every trigger is treated as
                successful (today's behavior, unchanged).
            action_effect_timeout_seconds: Longest wait for the VTherm to
                apply a triggered action before reporting the scheduler
                blocked (#256).
        """
        _LOGGER.debug("Initializing ControlPreheatingUseCase")
        self._preheat_actuator = preheat_actuator
        self._climate_data_reader = climate_data_reader
        self._action_effect_timeout_seconds = action_effect_timeout_seconds
        self._is_preheating_active = False
        self._preheating_target_time: datetime | None = None
        self._active_scheduler_entity: str | None = None
        self._active_timeslot: ScheduledTimeslot | None = None
        # The slot a no-effect command was last reported for: the report is made once per slot
        self._last_unapplied_slot: str | None = None
        # Told when a recovery finds a wake-up hold still running, so its timer can be re-armed
        self._on_hold_recovered: Callable[[ScheduledTimeslot, datetime], Awaitable[None]] | None = (
            None
        )

    async def cancel_preheating(
        self,
        scheduler_entity_id: str | None = None,
        reason: CancelReason = CancelReason.SLOT_CHANGED,
    ) -> None:
        """Cancel active preheating and revert to current scheduled state.

        Args:
            scheduler_entity_id: Scheduler entity to cancel action on.
                If None, uses the active scheduler entity.
            reason: Why the preheat is cancelled.
        """
        _LOGGER.debug(
            "Entering ControlPreheatingUseCase.cancel_preheating(scheduler=%s)",
            scheduler_entity_id,
        )

        effective_scheduler = scheduler_entity_id or self._active_scheduler_entity

        if self._is_preheating_active:
            timeslot = self._active_timeslot
            if not effective_scheduler or timeslot is None:
                _LOGGER.warning("Cannot cancel preheating: no scheduler entity available")
                _LOGGER.debug("Exiting ControlPreheatingUseCase.cancel_preheating() -> no-op")
                return
            _LOGGER.info(
                "Canceling preheating for scheduler %s - reverting to current scheduled state",
                effective_scheduler,
            )
            # The actuator reverts the thermostat to the current time's preset/temperature
            await self._preheat_actuator.cancel(timeslot, reason)
        else:
            _LOGGER.debug("No active preheating to cancel")

        # Mark preheating as inactive (but keep target_time for state tracking)
        # Target time may still be in future (e.g., reverted after a postponed start)
        self._is_preheating_active = False
        # Note: _preheating_target_time and _active_scheduler_entity are NOT cleared
        # They remain for state tracking and potential restart

        _LOGGER.debug("Exiting ControlPreheatingUseCase.cancel_preheating()")

    def set_on_hold_recovered(
        self, callback: Callable[[ScheduledTimeslot, datetime], Awaitable[None]] | None
    ) -> None:
        """Set the callback told when a recovery finds a hold still running.

        Args:
            callback: Async callback receiving the slot and when its hold ends, or None.
        """
        self._on_hold_recovered = callback

    def get_active_timeslot(self) -> ScheduledTimeslot | None:
        """Get the slot of the active preheating.

        Returns:
            The slot, or None when no preheating was started.
        """
        return self._active_timeslot

    async def end_hold(self, timeslot: ScheduledTimeslot) -> None:
        """End the hold of a slot: the actuator puts the earlier state back where that is safe.

        Args:
            timeslot: The slot whose hold ends.
        """
        await self._preheat_actuator.end_hold(timeslot)

    async def mark_preheating_complete(
        self, hold_until: datetime | None = None, handoff: bool = False
    ) -> None:
        """Mark preheating as finished without reverting anything.

        Used once the target slot has fired: the scheduler already applied the
        slot's setpoint, so reverting would undo it. The actuator is told so that it can
        forget what it recorded for the slot. Clearing the flag lets the next slot be anticipated.

        A wake-up slot with a hold is the exception: nothing applies the setting at its time, so
        the actuator keeps what it recorded until the hold ends.

        Args:
            hold_until: When the hold of a wake-up slot ends; None when there is no hold.
            handoff: True when a scheduler slot bounds the hold.
        """
        _LOGGER.debug("Marking preheating complete (target=%s)", self._preheating_target_time)
        timeslot = self._active_timeslot
        if self._is_preheating_active and timeslot is not None:
            if hold_until is not None and timeslot.hold is not None:
                await self._preheat_actuator.begin_hold(timeslot, hold_until, handoff)
            else:
                await self._preheat_actuator.cancel(timeslot, CancelReason.SLOT_REACHED)
        self._is_preheating_active = False

    async def recover_preheating(self, next_timeslot_of: NextTimeslotOf) -> RecoveryOutcome:
        """Pick up a preheat that was in progress before a restart or a reload.

        Args:
            next_timeslot_of: Gives the next timeslot of a scheduler entity. When the actuator
                holds a preheat whose slot is still its scheduler's next one, the preheat is
                marked active again, so that it is neither started a second time nor left
                unreported.

        Returns:
            What the reconciliation found; ``DEFERRED`` means a scheduler could not answer yet
            and the caller should ask again at its next cycle.
        """
        recovery = await self._preheat_actuator.recover(next_timeslot_of)
        if recovery.outcome is RecoveryOutcome.RESUMED and recovery.timeslot is not None:
            _LOGGER.info("Resuming the preheat in progress for %s", recovery.timeslot.timeslot_id)
            self._is_preheating_active = True
            self._preheating_target_time = recovery.timeslot.target_time
            self._active_scheduler_entity = recovery.timeslot.scheduler_entity
            self._active_timeslot = recovery.timeslot
        elif (
            recovery.outcome is RecoveryOutcome.HOLDING
            and recovery.timeslot is not None
            and recovery.hold_until is not None
            and self._on_hold_recovered is not None
        ):
            _LOGGER.info("Resuming the hold of %s", recovery.timeslot.timeslot_id)
            await self._on_hold_recovered(recovery.timeslot, recovery.hold_until)
        return recovery.outcome

    async def start_preheating(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        action: SlotAction | None = None,
        slot: ScheduledTimeslot | None = None,
    ) -> bool:
        """Start preheating by triggering scheduler action and verifying its effect.

        Args:
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            action: What the slot applies, when the scheduler gives one
            slot: The slot as the reader described it, with its identity and hold; rebuilt from
                the other arguments when absent

        Returns:
            True when there is nothing to fall back on: the action's effect was
            confirmed, the scheduler is a native schedule (nothing to verify),
            the VTherm's state could not be read (unproven failure, treated
            as success), or the climate was driven directly and did not take the action
            yet. In that last case preheating is *not* marked active, so the next
            recalculation tries again, and no other scheduler is tried. False only when a
            delegated action's mismatch was positively confirmed — the caller should attempt
            the next candidate scheduler instead.
        """
        _LOGGER.debug(
            "Entering ControlPreheatingUseCase.start_preheating(target_time=%s, temp=%.1f, scheduler=%s)",
            target_time.isoformat(),
            target_temp,
            scheduler_entity_id,
        )
        _LOGGER.info(
            "Starting preheating for target %s (%.1f°C)",
            target_time.isoformat(),
            target_temp,
        )

        timeslot = slot or self._build_timeslot(
            target_time, target_temp, scheduler_entity_id, action
        )
        result = await self._preheat_actuator.start(timeslot)

        if result in _RETRY_RESULTS:
            self._report_unapplied(timeslot, result)
            return True

        confirmed = await self._confirm_start(result, target_temp)

        if confirmed:
            self._is_preheating_active = True
            self._preheating_target_time = target_time
            self._active_scheduler_entity = scheduler_entity_id
            self._active_timeslot = timeslot
        else:
            _LOGGER.warning(
                "Scheduler action for %s had no effect (conditions likely unmet) - "
                "not marking preheating active",
                scheduler_entity_id,
            )

        _LOGGER.debug("Exiting ControlPreheatingUseCase.start_preheating() -> %s", confirmed)
        return confirmed

    def _report_unapplied(self, timeslot: ScheduledTimeslot, result: ActuationResult) -> None:
        """Say why a direct command left the climate as it was, once per slot.

        A command without effect is worth one INFO line; a guard that stopped it (the climate
        is off) is expected and stays at DEBUG. The next recalculation tries again either way.
        """
        if result is ActuationResult.SKIPPED:
            _LOGGER.debug(
                "Preheat of %s skipped: the climate is off or unavailable", timeslot.timeslot_id
            )
            return
        if self._last_unapplied_slot == timeslot.timeslot_id:
            _LOGGER.debug("Preheat of %s still not applied", timeslot.timeslot_id)
            return
        self._last_unapplied_slot = timeslot.timeslot_id
        _LOGGER.info(
            "The climate did not take the action of the slot starting at %s: IHP tries again at "
            "the next recalculation",
            timeslot.target_time.isoformat(),
        )

    @staticmethod
    def _build_timeslot(
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        action: SlotAction | None,
    ) -> ScheduledTimeslot:
        """Rebuild the slot the readers described, with the identity they gave it."""
        return ScheduledTimeslot(
            target_time=target_time,
            target_temp=target_temp,
            timeslot_id=f"{scheduler_entity_id}_{target_time.isoformat()}",
            scheduler_entity=scheduler_entity_id,
            action=action,
        )

    async def _confirm_start(self, result: ActuationResult, target_temp: float) -> bool:
        """Turn the actuator's result into "may the preheat proceed?".

        ``ATTEMPTED`` (a delegated command) is verified on the thermostat's target; a command
        the actuator confirmed itself, or one never sent by design, needs no verification.

        Args:
            result: What the actuator reported.
            target_temp: The temperature a delegated action was expected to apply.

        Returns:
            True when the preheat may proceed; False when the effect was disproved.
        """
        if result is ActuationResult.ATTEMPTED:
            return await self._verify_action_effect(target_temp)
        return result in (ActuationResult.APPLIED, ActuationResult.UNSUPPORTED)

    async def _verify_action_effect(self, target_temp: float) -> bool:
        """Verify whether a triggered action actually applied ``target_temp``.

        scheduler-component returns from ``run_action`` before the VTherm has
        applied the action (#256). A mismatch therefore only proves a block
        once the VTherm had the chance to apply it: until the action effect
        timeout, each VTherm state change is read again.

        Args:
            target_temp: The temperature the action was expected to apply.

        Returns:
            True when there is nothing to disprove (no reader
            configured, or the VTherm state is unreadable) or the resulting
            target temperature matches within tolerance. False only when it
            still does not match at the timeout.
        """
        reader = self._climate_data_reader
        if reader is None:
            return True

        deadline = monotonic() + self._action_effect_timeout_seconds
        while True:
            resulting_temp = reader.get_target_temperature()
            if resulting_temp is None:
                return True
            if abs(resulting_temp - target_temp) <= TARGET_TEMP_MATCH_TOLERANCE_C:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0 or not await reader.wait_for_state_change(remaining):
                _LOGGER.debug("VTherm target still %.1f°C at the timeout", resulting_temp)
                return False

    def is_preheating_active(self) -> bool:
        """Check if preheating is currently active.

        Returns:
            True if preheating is active, False otherwise
        """
        return self._is_preheating_active

    def get_preheating_target_time(self) -> datetime | None:
        """Get the target time for active preheating.

        Returns:
            Target time if preheating is active, None otherwise
        """
        return self._preheating_target_time

    def get_active_scheduler_entity(self) -> str | None:
        """Get the active scheduler entity.

        Returns:
            Scheduler entity ID if active, None otherwise
        """
        return self._active_scheduler_entity
