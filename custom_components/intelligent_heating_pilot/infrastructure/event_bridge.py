"""Home Assistant event bridge - translates HA events to application service calls.

This infrastructure component listens to HA entity state changes and delegates
to the application service.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .vtherm_compat import get_vtherm_attribute

if TYPE_CHECKING:
    from datetime import datetime
    
    from ..application import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class HAEventBridge:
    """Bridges Home Assistant events to application service.
    
    This infrastructure component:
    - Listens to relevant HA entity state changes
    - Translates events to application service calls
    - Manages state change listeners lifecycle
    
    NO business logic - pure event routing.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        application_service: "HeatingApplicationService",
        vtherm_entity_id: str,
        scheduler_entity_ids: list[str],
        monitored_entity_ids: list[str] | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the event bridge.
        
        Args:
            hass: Home Assistant instance
            application_service: Application service to delegate to
            vtherm_entity_id: VTherm entity to monitor for slopes
            scheduler_entity_ids: Scheduler entities to monitor
            monitored_entity_ids: Additional entities to monitor (humidity, etc.)
            entry_id: Config entry ID for event filtering
        """
        self._hass = hass
        self._app_service = application_service
        self._vtherm_entity_id = vtherm_entity_id
        self._scheduler_entity_ids = scheduler_entity_ids
        self._monitored_entity_ids = monitored_entity_ids or []
        self._entry_id = entry_id
        
        # Track all entities that should trigger updates
        self._tracked_entities = [vtherm_entity_id] + scheduler_entity_ids + self._monitored_entity_ids
        
        # Listener cleanup callbacks
        self._listeners: list = []
        
        # Debouncing state
        self._ignore_vtherm_until: datetime | None = None
    
    def setup_listeners(self) -> None:
        """Setup all event listeners."""
        @callback
        def _on_entity_changed(event: Event[EventStateChangedData]) -> None:
            """Handle entity state change events."""
            entity_id = event.data.get("entity_id")
            
            if entity_id not in self._tracked_entities:
                return
            
            # VTherm-specific handling for slope learning
            if entity_id == self._vtherm_entity_id:
                self._handle_vtherm_change(event)
            else:
                # Other entities just trigger recalculation
                _LOGGER.debug("Entity %s changed, triggering update", entity_id)
                self._hass.async_create_task(
                    self._recalculate_and_publish()
                )
        
        # Register state change listener
        unsub = async_track_state_change_event(
            self._hass,
            self._tracked_entities,
            _on_entity_changed
        )
        self._listeners.append(unsub)
        
        _LOGGER.info("Event bridge tracking %d entities", len(self._tracked_entities))
    
    def _handle_vtherm_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle VTherm state changes (slope learning + update).
        
        Args:
            event: State change event
        """
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        
        if not old_state or not new_state:
            return
        
        # Check if we should ignore (self-induced change)
        if self._ignore_vtherm_until and dt_util.now() < self._ignore_vtherm_until:
            _LOGGER.debug("Ignoring self-induced VTherm change")
            return
        
        # Extract slope changes (v8.0.0+ compatible)
        old_slope = get_vtherm_attribute(old_state, "temperature_slope")
        new_slope = get_vtherm_attribute(new_state, "temperature_slope")
        
        # Extract temperature changes (v8.0.0+ compatible)
        old_temp = get_vtherm_attribute(old_state, "current_temperature")
        new_temp = get_vtherm_attribute(new_state, "current_temperature")
        
        slope_changed = old_slope != new_slope
        temp_changed = old_temp != new_temp
        
        if not (slope_changed or temp_changed):
            return
        
        if slope_changed:
            _LOGGER.debug("VTherm slope changed: %s -> %s", old_slope, new_slope)
            # Process slope learning
            if new_slope is not None:
                try:
                    slope_val = float(new_slope)
                    self._hass.async_create_task(
                        self._app_service.process_slope_update(slope_val)
                    )
                except (ValueError, TypeError):
                    _LOGGER.debug("Invalid slope value: %s", new_slope)
        
        if temp_changed:
            _LOGGER.debug("VTherm temperature changed: %s -> %s", old_temp, new_temp)
        
        # Trigger recalculation and publish to sensors
        self._hass.async_create_task(
            self._recalculate_and_publish()
        )
    
    async def _recalculate_and_publish(self) -> None:
        """Recalculate anticipation and publish event for sensors."""
        anticipation_data = await self._app_service.calculate_and_schedule_anticipation()
        
        if anticipation_data:
            # Publish event for sensors with data
            self._hass.bus.async_fire(
                "intelligent_heating_pilot_anticipation_calculated",
                {
                    "entry_id": self._entry_id,
                    "anticipated_start_time": anticipation_data["anticipated_start_time"].isoformat(),
                    "next_schedule_time": anticipation_data["next_schedule_time"].isoformat(),
                    "next_target_temperature": anticipation_data["next_target_temperature"],
                    "anticipation_minutes": anticipation_data["anticipation_minutes"],
                    "current_temp": anticipation_data["current_temp"],
                    "learned_heating_slope": anticipation_data["learned_heating_slope"],
                    "confidence_level": anticipation_data["confidence_level"],
                    "scheduler_entity": anticipation_data.get("scheduler_entity", ""),
                },
            )
            _LOGGER.debug("Published anticipation event for sensors")
        else:
            # Publish event to clear sensor values (set to unknown)
            self._hass.bus.async_fire(
                "intelligent_heating_pilot_anticipation_calculated",
                {
                    "entry_id": self._entry_id,
                    "clear_values": True,  # Signal to sensors to clear their values
                },
            )
            _LOGGER.debug("Published clear event for sensors")
    
    def ignore_vtherm_changes_for(self, seconds: int = 10) -> None:
        """Temporarily ignore VTherm changes (used after self-induced changes).
        
        Args:
            seconds: How long to ignore changes
        """
        from datetime import timedelta
        self._ignore_vtherm_until = dt_util.now() + timedelta(seconds=seconds)
    
    def cleanup(self) -> None:
        """Cleanup all event listeners."""
        for unsub in self._listeners:
            unsub()
        self._listeners.clear()
        _LOGGER.info("Event bridge cleaned up")
