"""Home Assistant scheduler commander adapter.

This adapter implements ISchedulerCommander by calling Home Assistant
scheduler services to trigger heating actions.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant

from ...domain.interfaces.scheduler_commander_interface import ISchedulerCommander
from .utils import get_entity_name

_LOGGER = logging.getLogger(__name__)

# Scheduler service configuration
SCHEDULER_DOMAIN = "scheduler"
SERVICE_RUN_ACTION = "run_action"

# Native HA schedule helpers have no service that applies a slot: scheduler.run_action
# belongs to HACS Scheduler and only accepts its switch entities. IHP delegates
# actuation to HACS Scheduler, so for native schedules it only computes the
# anticipation and exposes it as sensors.
NATIVE_SCHEDULE_PREFIX = "schedule."


class HASchedulerCommander(ISchedulerCommander):
    """Home Assistant implementation of scheduler commander.

    Executes scheduler commands using the scheduler-component's run_action service.
    See: https://github.com/nielsfaber/scheduler-component/#schedulerrun_action

    This adapter contains NO business logic - it only translates domain
    requests into Home Assistant service calls. Native ``schedule.*`` entities
    have no such service, so requests on them are not translated (no-op).
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the scheduler commander adapter.

        Args:
            hass: Home Assistant instance
            scheduler_entity_id: The scheduler entity ID to control
        """
        self._hass = hass

    async def run_action(self, target_time: datetime, scheduler_entity_id: str) -> bool:
        """Trigger a scheduler action for a specific timeslot.

        This will start heating in the mode configured in the scheduler
        for the timeslot at the given time. Never bypasses the scheduler's
        own conditions (no ``skip_conditions`` override).

        Args:
            target_time: The time of the scheduler timeslot to trigger
            scheduler_entity_id: Scheduler entity ID to control

        Returns:
            ``True`` if an actuation attempt was made on the underlying HACS
            Scheduler (whether or not its conditions ultimately let the
            action through — that is for the caller to verify separately).
            ``False`` for a native HA schedule entity, which this adapter
            never actuates (compute-only).

        Raises:
            ValueError: If scheduler entity is not configured
        """
        if not scheduler_entity_id:
            _LOGGER.error("Cannot run action: no scheduler entity configured")
            raise ValueError("Scheduler entity ID not configured")

        if self._is_native_schedule(scheduler_entity_id):
            _LOGGER.info(
                "[%s] Native schedule: preheating computed for %s, no scheduler action "
                "triggered (actuation requires HACS Scheduler)",
                get_entity_name(self._hass, scheduler_entity_id),
                target_time.strftime("%H:%M"),
            )
            return False

        # Format time as HH:MM for scheduler service
        trigger_time_str = target_time.strftime("%H:%M")

        device_name = get_entity_name(self._hass, scheduler_entity_id)
        _LOGGER.info("[%s] Triggering scheduler action at time %s", device_name, trigger_time_str)

        try:
            await self._hass.services.async_call(
                SCHEDULER_DOMAIN,
                SERVICE_RUN_ACTION,
                {
                    "entity_id": scheduler_entity_id,
                    "time": trigger_time_str,
                    "skip_conditions": False,  # Respect scheduler conditions
                },
                blocking=True,
            )
            _LOGGER.debug("Scheduler action triggered successfully")
            return True
        except Exception as err:
            _LOGGER.error(
                "Failed to trigger scheduler action for %s: %s",
                scheduler_entity_id,
                err,
                exc_info=True,
            )
            raise

    async def cancel_action(self, scheduler_entity_id: str) -> None:
        """Cancel current scheduler action and return to current timeslot.

        This is used to stop overshoot by reverting to the mode configured
        for the current time (now()).

        Note: The scheduler-component doesn't have a direct "cancel" service.
        This implementation triggers the action for "now" which effectively
        reverts to the current scheduled state.

        Args:
            scheduler_entity_id: Scheduler entity ID to control

        Raises:
            ValueError: If scheduler entity is not configured
        """
        if not scheduler_entity_id:
            _LOGGER.error("Cannot cancel action: no scheduler entity configured")
            raise ValueError("Scheduler entity ID not configured")

        if self._is_native_schedule(scheduler_entity_id):
            _LOGGER.debug(
                "Native schedule %s: nothing to cancel, no scheduler action was triggered",
                scheduler_entity_id,
            )
            return

        # Get current time
        from homeassistant.util import dt as dt_util

        now = dt_util.now()
        current_time_str = now.strftime("%H:%M")

        device_name = get_entity_name(self._hass, scheduler_entity_id)
        _LOGGER.info(
            "[%s] Canceling scheduler action by reverting to current time %s",
            device_name,
            current_time_str,
        )

        try:
            await self._hass.services.async_call(
                SCHEDULER_DOMAIN,
                SERVICE_RUN_ACTION,
                {
                    "entity_id": scheduler_entity_id,
                    "time": current_time_str,
                    "skip_conditions": False,
                },
                blocking=True,
            )
            _LOGGER.debug("Scheduler action canceled successfully")
        except Exception as err:
            _LOGGER.error(
                "Failed to cancel scheduler action for %s: %s",
                scheduler_entity_id,
                err,
                exc_info=True,
            )
            raise

    @staticmethod
    def _is_native_schedule(scheduler_entity_id: str) -> bool:
        """Return True for a native HA schedule helper (no HACS service to call)."""
        return scheduler_entity_id.startswith(NATIVE_SCHEDULE_PREFIX)
