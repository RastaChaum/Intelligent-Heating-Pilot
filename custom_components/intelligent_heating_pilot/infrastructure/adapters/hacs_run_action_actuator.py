"""HACS Scheduler actuator: delegates the preheat to the scheduler's own run-action command.

Implements IPreheatActuator for HACS Scheduler. IHP calls ``scheduler.run_action`` at the
anticipated start so that the scheduler applies the upcoming slot early, with the scheduler's
own conditions still checked. This adapter contains no business logic: it only translates a
domain request into a Home Assistant service call.

See: https://github.com/nielsfaber/scheduler-component/#schedulerrun_action
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.interfaces.preheat_actuator_interface import IPreheatActuator, NextTimeslotOf
from ...domain.value_objects.actuation_result import ActuationResult
from ...domain.value_objects.cancel_reason import CancelReason
from ...domain.value_objects.preheat_recovery import PreheatRecovery, RecoveryOutcome
from ...domain.value_objects.scheduled_timeslot import ScheduledTimeslot
from .utils import get_entity_name

_LOGGER = logging.getLogger(__name__)

# Scheduler service configuration
SCHEDULER_DOMAIN = "scheduler"
SERVICE_RUN_ACTION = "run_action"

# ``scheduler.run_action`` belongs to HACS Scheduler and only accepts its switch entities.
# Routing never sends a native ``schedule.*`` helper here; this guard keeps a misrouted one
# from raising ServiceNotFound on every start attempt.
NATIVE_SCHEDULE_PREFIX = "schedule."


class HacsRunActionActuator(IPreheatActuator):
    """Starts and cancels a preheat through HACS Scheduler's ``run_action`` service."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the actuator.

        Args:
            hass: Home Assistant instance.
        """
        self._hass = hass

    async def start(self, timeslot: ScheduledTimeslot) -> ActuationResult:
        """Trigger the scheduler's action for the slot's time.

        Never bypasses the scheduler's own conditions (no ``skip_conditions`` override).

        Args:
            timeslot: The slot to preheat for.

        Returns:
            ``ATTEMPTED`` once the command was sent: whether the scheduler's conditions let
            the action through is for the caller to verify. ``UNSUPPORTED`` for a native
            schedule entity, which this actuator never actuates.

        Raises:
            ValueError: If the slot has no scheduler entity.
        """
        entity_id = self._require_entity(timeslot)
        if entity_id.startswith(NATIVE_SCHEDULE_PREFIX):
            _LOGGER.debug(
                "[%s] Native schedule: nothing to trigger", get_entity_name(self._hass, entity_id)
            )
            return ActuationResult.UNSUPPORTED
        await self._run_action(entity_id, timeslot.target_time)
        return ActuationResult.ATTEMPTED

    async def cancel(self, timeslot: ScheduledTimeslot, reason: CancelReason) -> None:
        """Revert to the scheduler's current slot, which stops an overshoot.

        The scheduler-component has no "cancel" service: triggering the action for "now"
        effectively reverts to the current scheduled state. Once the slot has been reached the
        scheduler already applied its own action, so nothing is sent.

        Args:
            timeslot: The slot whose preheat is cancelled.
            reason: Why it is cancelled.

        Raises:
            ValueError: If the slot has no scheduler entity.
        """
        entity_id = self._require_entity(timeslot)
        if reason is CancelReason.SLOT_REACHED or entity_id.startswith(NATIVE_SCHEDULE_PREFIX):
            _LOGGER.debug("Nothing to revert for %s (%s)", entity_id, reason.value)
            return
        _LOGGER.info(
            "[%s] Canceling scheduler action by reverting to the current time",
            get_entity_name(self._hass, entity_id),
        )
        await self._run_action(entity_id, dt_util.now())

    async def recover(self, next_timeslot_of: NextTimeslotOf) -> PreheatRecovery:
        """Nothing is persisted for a delegated preheat: there is nothing to recover.

        Args:
            next_timeslot_of: Unused.

        Returns:
            Always ``NOTHING``.
        """
        return PreheatRecovery(RecoveryOutcome.NOTHING)

    @staticmethod
    def _require_entity(timeslot: ScheduledTimeslot) -> str:
        if not timeslot.scheduler_entity:
            _LOGGER.error("Cannot act: no scheduler entity configured")
            raise ValueError("Scheduler entity ID not configured")
        return timeslot.scheduler_entity

    async def _run_action(self, entity_id: str, at: datetime) -> None:
        """Call ``scheduler.run_action`` for the slot at the given time."""
        device_name = get_entity_name(self._hass, entity_id)
        time_str = at.strftime("%H:%M")
        _LOGGER.info("[%s] Triggering scheduler action at time %s", device_name, time_str)
        try:
            await self._hass.services.async_call(
                SCHEDULER_DOMAIN,
                SERVICE_RUN_ACTION,
                {"entity_id": entity_id, "time": time_str, "skip_conditions": False},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error(
                "Failed to trigger scheduler action for %s: %s", entity_id, err, exc_info=True
            )
            raise
