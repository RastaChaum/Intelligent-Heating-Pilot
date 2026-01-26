"""Home Assistant timer scheduler adapter.

This adapter implements ITimerScheduler using Home Assistant's
async_track_point_in_time API.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Awaitable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time

from ...domain.interfaces import ITimerScheduler

_LOGGER = logging.getLogger(__name__)


class HATimerScheduler(ITimerScheduler):
    """Home Assistant implementation of timer scheduler.
    
    Uses Home Assistant's event loop to schedule callbacks at specific times.
    This adapter contains NO business logic - it only wraps HA's timer API.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the timer scheduler adapter.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
    
    def schedule_timer(
        self,
        target_time: datetime,
        callback_func: Callable[[], Awaitable[None]],
    ) -> Callable[[], None]:
        """Schedule a callback to execute at a specific time.
        
        Args:
            target_time: When to execute the callback
            callback_func: Async function to execute at target_time
            
        Returns:
            Cancel function that can be called to cancel the timer
        """
        @callback
        def _timer_callback(_now: datetime) -> None:
            """Wrapper callback that creates async task."""
            self._hass.async_create_task(callback_func())
        
        # Schedule the timer and return the cancel function
        cancel_func = async_track_point_in_time(
            self._hass,
            _timer_callback,
            target_time,
        )
        
        _LOGGER.debug(
            "Timer scheduled for %s",
            target_time.isoformat(),
        )
        
        return cancel_func
