"""Home Assistant scheduler commander adapter.

This adapter implements ISchedulerCommander by calling Home Assistant
scheduler services to trigger heating actions.
"""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant

from ...domain.interfaces import ISchedulerCommander

_LOGGER = logging.getLogger(__name__)

# Scheduler service configuration
SCHEDULER_DOMAIN = "scheduler"
SERVICE_RUN_ACTION = "run_action"


class HASchedulerCommander(ISchedulerCommander):
    """Home Assistant implementation of scheduler commander.
    
    Executes scheduler commands using the scheduler-component's run_action service.
    See: https://github.com/nielsfaber/scheduler-component/#schedulerrun_action
    
    This adapter contains NO business logic - it only translates domain
    requests into Home Assistant service calls.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the scheduler commander adapter.
        
        Args:
            hass: Home Assistant instance
            scheduler_entity_id: The scheduler entity ID to control
        """
        self._hass = hass
    
    async def run_action(self, target_time: datetime, scheduler_entity_id: str) -> None:
        """Trigger a scheduler action for a specific timeslot.
        
        This will start heating in the mode configured in the scheduler
        for the timeslot at the given time.
        
        Args:
            target_time: The time of the scheduler timeslot to trigger
            
        Raises:
            ValueError: If scheduler entity is not configured
        """
        if not scheduler_entity_id:
            _LOGGER.error("Cannot run action: no scheduler entity configured")
            raise ValueError("Scheduler entity ID not configured")
        
        # Format time as HH:MM for scheduler service
        trigger_time_str = target_time.strftime("%H:%M")
        
        _LOGGER.info(
            "Triggering scheduler action for %s at time %s",
            scheduler_entity_id,
            trigger_time_str
        )
        
        try:
            await self._hass.services.async_call(
                SCHEDULER_DOMAIN,
                SERVICE_RUN_ACTION,
                {
                    "entity_id": scheduler_entity_id,
                    "time": trigger_time_str,
                    "skip_conditions": False  # Respect scheduler conditions
                },
                blocking=True,
            )
            _LOGGER.debug("Scheduler action triggered successfully")
        except Exception as err:
            _LOGGER.error(
                "Failed to trigger scheduler action for %s: %s",
                scheduler_entity_id,
                err,
                exc_info=True
            )
            raise
    
    async def cancel_action(self, scheduler_entity_id: str) -> None:
        """Cancel current scheduler action and return to current timeslot.
        
        This is used to stop overshoot by reverting to the mode configured
        for the current time (now()).
        
        Note: The scheduler-component doesn't have a direct "cancel" service.
        This implementation triggers the action for "now" which effectively
        reverts to the current scheduled state.
        """
        if not scheduler_entity_id:
            _LOGGER.error("Cannot cancel action: no scheduler entity configured")
            raise ValueError("Scheduler entity ID not configured")
        
        # Get current time
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        current_time_str = now.strftime("%H:%M")
        
        _LOGGER.info(
            "Canceling scheduler action for %s by reverting to current time %s",
            scheduler_entity_id,
            current_time_str
        )
        
        try:
            await self._hass.services.async_call(
                SCHEDULER_DOMAIN,
                SERVICE_RUN_ACTION,
                {
                    "entity_id": scheduler_entity_id,
                    "time": current_time_str,
                    "skip_conditions": False
                },
                blocking=True,
            )
            _LOGGER.debug("Scheduler action canceled successfully")
        except Exception as err:
            _LOGGER.error(
                "Failed to cancel scheduler action for %s: %s",
                scheduler_entity_id,
                err,
                exc_info=True
            )
            raise
