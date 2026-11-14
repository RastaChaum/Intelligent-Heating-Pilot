"""Control Preheating Use Case.

This use case controls the preheating state (start/cancel).
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING

from ...domain.constants import ACTION_EFFECT_TIMEOUT_SECONDS, TARGET_TEMP_MATCH_TOLERANCE_C
from ...domain.value_objects import ActuationResult, CancelReason, ScheduledTimeslot

if TYPE_CHECKING:
    from datetime import datetime

    from ...domain.interfaces import IClimateDataReader, IPreheatActuator

_LOGGER = logging.getLogger(__name__)


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

    async def cancel_preheating(self, scheduler_entity_id: str | None = None) -> None:
        """Cancel active preheating and revert to current scheduled state.

        Args:
            scheduler_entity_id: Scheduler entity to cancel action on.
                If None, uses the active scheduler entity.
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
            await self._preheat_actuator.cancel(timeslot, CancelReason.SLOT_CHANGED)
        else:
            _LOGGER.debug("No active preheating to cancel")

        # Mark preheating as inactive (but keep target_time for state tracking)
        # Target time may still be in future (e.g., reverted after a postponed start)
        self._is_preheating_active = False
        # Note: _preheating_target_time and _active_scheduler_entity are NOT cleared
        # They remain for state tracking and potential restart

        _LOGGER.debug("Exiting ControlPreheatingUseCase.cancel_preheating()")

    def mark_preheating_complete(self) -> None:
        """Mark preheating as finished without commanding the scheduler.

        Used once the target slot has fired: the scheduler already applied the
        slot's setpoint, so reverting would undo it. Clearing the flag lets the
        next slot be anticipated.
        """
        _LOGGER.debug("Marking preheating complete (target=%s)", self._preheating_target_time)
        self._is_preheating_active = False

    async def start_preheating(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> bool:
        """Start preheating by triggering scheduler action and verifying its effect.

        Args:
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger

        Returns:
            True when preheating may proceed normally: the action's effect was
            confirmed, the scheduler is a native schedule (nothing to verify),
            or the VTherm's state could not be read (unproven failure, treated
            as success). False only when a mismatch was positively confirmed —
            the caller should attempt the next candidate scheduler instead.
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

        timeslot = self._build_timeslot(target_time, target_temp, scheduler_entity_id)
        result = await self._preheat_actuator.start(timeslot)

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

    @staticmethod
    def _build_timeslot(
        target_time: datetime, target_temp: float, scheduler_entity_id: str
    ) -> ScheduledTimeslot:
        """Rebuild the slot the readers described, with the identity they gave it."""
        return ScheduledTimeslot(
            target_time=target_time,
            target_temp=target_temp,
            timeslot_id=f"{scheduler_entity_id}_{target_time.isoformat()}",
            scheduler_entity=scheduler_entity_id,
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
            return await self._verify_action_effect(True, target_temp)
        return result in (ActuationResult.APPLIED, ActuationResult.UNSUPPORTED)

    async def _verify_action_effect(self, attempted: bool, target_temp: float) -> bool:
        """Verify whether a triggered action actually applied ``target_temp``.

        scheduler-component returns from ``run_action`` before the VTherm has
        applied the action (#256). A mismatch therefore only proves a block
        once the VTherm had the chance to apply it: until the action effect
        timeout, each VTherm state change is read again.

        Args:
            attempted: Whether an actuation attempt was made (False for a
                native schedule, which is never actuated).
            target_temp: The temperature the action was expected to apply.

        Returns:
            True when there is nothing to disprove (no attempt, no reader
            configured, or the VTherm state is unreadable) or the resulting
            target temperature matches within tolerance. False only when it
            still does not match at the timeout.
        """
        reader = self._climate_data_reader
        if not attempted or reader is None:
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
