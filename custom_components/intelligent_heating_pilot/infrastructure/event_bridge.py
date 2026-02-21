"""Home Assistant event bridge - translates HA events to orchestrator calls.

This infrastructure component listens to HA entity state changes and delegates
to the orchestrator.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .vtherm_compat import get_vtherm_attribute

if TYPE_CHECKING:
    from datetime import datetime

    from ..application import HeatingOrchestrator

_LOGGER = logging.getLogger(__name__)

# Minimum change in monitored sensor value (humidity %, cloud coverage %) to
# trigger a recalculation.  Small fluctuations below this threshold are ignored.
_MONITORED_ENTITY_CHANGE_THRESHOLD = 3.0

# Tolerance in seconds for anticipated_start_time comparison.  Changes smaller
# than this are not considered meaningful enough to re-publish the event.
_ANTICIPATION_TIME_TOLERANCE_SECONDS = 60


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
        orchestrator: HeatingOrchestrator,
        vtherm_entity_id: str,
        scheduler_entity_ids: list[str],
        monitored_entity_ids: list[str] | None = None,
        entry_id: str | None = None,
        get_ihp_enabled_func: Callable[[], bool] | None = None,
    ) -> None:
        """Initialize the event bridge.

        Args:
            hass: Home Assistant instance
            orchestrator: Orchestrator to delegate to
            vtherm_entity_id: VTherm entity to monitor for slopes
            scheduler_entity_ids: Scheduler entities to monitor
            monitored_entity_ids: Additional entities to monitor (humidity, etc.)
            entry_id: Config entry ID for event filtering
            get_ihp_enabled_func: Callback function to get current IHP enabled state
        """
        self._hass = hass
        self._orchestrator = orchestrator
        self._vtherm_entity_id = vtherm_entity_id
        self._scheduler_entity_ids = scheduler_entity_ids
        self._monitored_entity_ids = monitored_entity_ids or []
        self._get_ihp_enabled = get_ihp_enabled_func or (lambda: True)
        self._entry_id = entry_id

        # Track all entities that should trigger updates
        self._tracked_entities = (
            [vtherm_entity_id] + scheduler_entity_ids + self._monitored_entity_ids
        )

        # Listener cleanup callbacks
        self._listeners: list = []

        # Debouncing state
        self._ignore_vtherm_until: datetime | None = None

        # Deduplication: remember the last event data that was published so we
        # can skip firing when nothing meaningful has changed.
        self._last_published_data: dict | None = None

    def setup_listeners(self) -> None:
        """Setup all event listeners."""

        @callback
        def _on_entity_changed(event: Event[EventStateChangedData]) -> None:
            """Handle entity state change events.

            All listened entities trigger _recalculate_and_publish(), which routes
            to appropriate orchestrator method based on event source.
            """
            entity_id = event.data.get("entity_id")

            if entity_id not in self._tracked_entities:
                return

            # VTherm-specific handling for slope learning
            if entity_id == self._vtherm_entity_id:
                self._handle_vtherm_change(event)
            elif entity_id in self._scheduler_entity_ids:
                # Only trigger for meaningful scheduler state changes
                self._trigger_recalculate_if_meaningful(
                    self._has_meaningful_scheduler_change(event), entity_id
                )
            else:
                # Monitored entity (humidity, cloud cover) – apply threshold filter
                self._trigger_recalculate_if_meaningful(
                    self._has_meaningful_monitored_change(event), entity_id
                )

        # Register state change listener
        unsub = async_track_state_change_event(
            self._hass, self._tracked_entities, _on_entity_changed
        )
        self._listeners.append(unsub)

        _LOGGER.debug("Event bridge tracking %d entities", len(self._tracked_entities))

    # ------------------------------------------------------------------
    # Smart filtering helpers
    # ------------------------------------------------------------------

    def _trigger_recalculate_if_meaningful(self, meaningful: bool, entity_id: str) -> None:
        """Trigger recalculation when the entity change is meaningful.

        Logs the outcome at DEBUG level to aid diagnostics without noise.
        """
        if meaningful:
            _LOGGER.debug("Entity %s changed meaningfully, triggering update", entity_id)
            self._hass.async_create_task(self._recalculate_and_publish())
        else:
            _LOGGER.debug("Entity %s change not actionable, skipping recalculation", entity_id)

    def _has_meaningful_scheduler_change(self, event: Event[EventStateChangedData]) -> bool:
        """Return True only when a scheduler state change is actionable for IHP.

        Ignores attribute-only updates that do not affect the IHP schedule
        (e.g., internal counters, last_triggered, etc.).  Only the following
        changes are considered meaningful:

        - The enabled / disabled state (on / off) toggled.
        - The ``next_trigger`` timestamp changed (different upcoming slot).
        - The ``actions`` attribute changed (different target temperature / preset).
        """
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not old_state or not new_state:
            return True

        # Enabled / disabled toggle
        if old_state.state != new_state.state:
            return True

        old_attrs = old_state.attributes
        new_attrs = new_state.attributes

        # Next occurrence time changed
        if old_attrs.get("next_trigger") != new_attrs.get("next_trigger"):
            return True

        # Target temperature / actions changed
        return bool(old_attrs.get("actions") != new_attrs.get("actions"))

    def _has_meaningful_monitored_change(self, event: Event[EventStateChangedData]) -> bool:
        """Return True only when a monitored sensor value changed significantly.

        Tiny fluctuations in humidity or cloud coverage sensors are ignored.
        Availability transitions are always considered meaningful.
        """
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not old_state or not new_state:
            return True

        _unavailable = {"unavailable", "unknown"}
        old_unavailable = old_state.state in _unavailable
        new_unavailable = new_state.state in _unavailable

        # Availability transition is always actionable
        if old_unavailable != new_unavailable:
            return True

        # Both unavailable – nothing changed
        if old_unavailable and new_unavailable:
            return False

        try:
            old_val = float(str(old_state.state))
            new_val = float(str(new_state.state))
            return abs(new_val - old_val) >= _MONITORED_ENTITY_CHANGE_THRESHOLD
        except (TypeError, ValueError):
            # Non-numeric state: trigger on any state string change
            return bool(old_state.state != new_state.state)

    def _is_meaningful_change_from_last(self, new_data: dict) -> bool:
        """Return True when *new_data* differs meaningfully from the last published event.

        Prevents flooding sensors with identical or near-identical events.
        """
        last = self._last_published_data
        if last is None:
            return True

        # Core schedule fields – any difference is significant
        for key in ("next_schedule_time", "next_target_temperature", "scheduler_entity"):
            if new_data.get(key) != last.get(key):
                return True

        # Current indoor temperature (0.1 °C tolerance)
        new_temp = new_data.get("current_temp")
        last_temp = last.get("current_temp")
        # Transition between "no data" and a real temperature is always meaningful
        if (new_temp is None) != (last_temp is None):
            return True
        if new_temp is not None and last_temp is not None and abs(new_temp - last_temp) >= 0.1:
            return True

        # Learned heating slope (0.05 °C/h tolerance)
        new_lhs = new_data.get("learned_heating_slope")
        last_lhs = last.get("learned_heating_slope")
        # Transition between "no data" and a real slope is always meaningful
        if (new_lhs is None) != (last_lhs is None):
            return True
        if new_lhs is not None and last_lhs is not None and abs(new_lhs - last_lhs) >= 0.05:
            return True

        # Anticipated start time (1-minute tolerance)
        new_start = new_data.get("anticipated_start_time")
        last_start = last.get("anticipated_start_time")

        # If both are equal (including both None or identical strings/datetimes), no meaningful change
        if new_start == last_start:
            return False

        # If one is None and the other is not, this is a meaningful change
        if new_start is None or last_start is None:
            return True

        try:
            new_dt = dt_util.parse_datetime(new_start) if isinstance(new_start, str) else new_start
            last_dt = (
                dt_util.parse_datetime(last_start) if isinstance(last_start, str) else last_start
            )
            if new_dt is None or last_dt is None:
                return True
            if abs((new_dt - last_dt).total_seconds()) >= _ANTICIPATION_TIME_TOLERANCE_SECONDS:
                return True
        except (TypeError, ValueError, AttributeError):
            return True

        return False

    def _handle_vtherm_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle VTherm state changes (temperature filter + recalculation trigger).

        Args:
            event: State change event
        """
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not old_state or not new_state:
            return

        # Check if we should ignore (self-induced change)
        if self._ignore_vtherm_until and dt_util.now() < self._ignore_vtherm_until:
            _LOGGER.debug("Ignoring self-induced VTherm change")
            return

        # Extract temperature changes (v8.0.0+ compatible)
        old_temp = get_vtherm_attribute(old_state, "current_temperature")
        new_temp = get_vtherm_attribute(new_state, "current_temperature")

        if old_temp == new_temp:
            _LOGGER.debug("VTherm change but temperature unchanged, skipping")
            return

        _LOGGER.debug("VTherm temperature changed: %s -> %s", old_temp, new_temp)
        self._hass.async_create_task(self._recalculate_and_publish())

    async def _recalculate_and_publish(self) -> None:
        """Recalculate anticipation and publish event for sensors if data changed.

        Always fires the same unified event structure. Scheduling/clearing is
        expressed via None values (never a ``clear_values`` flag) so that all
        sensors share a single, consistent event shape.
        """
        anticipation_data = await self._orchestrator.calculate_and_schedule_anticipation(
            ihp_enabled=self._get_ihp_enabled()
        )

        if not anticipation_data:
            anticipation_data = {}

        # Build unified event structure (same keys always, None for missing values)
        has_complete_data = (
            anticipation_data.get("anticipated_start_time") is not None
            and anticipation_data.get("next_schedule_time") is not None
        )

        if has_complete_data:
            event_data: dict = {
                "entry_id": self._entry_id,
                "anticipated_start_time": anticipation_data["anticipated_start_time"].isoformat(),
                "next_schedule_time": anticipation_data["next_schedule_time"].isoformat(),
                "next_target_temperature": anticipation_data.get("next_target_temperature"),
                "anticipation_minutes": anticipation_data.get("anticipation_minutes"),
                "current_temp": anticipation_data.get("current_temp"),
                "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
                "confidence_level": anticipation_data.get("confidence_level"),
                "scheduler_entity": anticipation_data.get("scheduler_entity"),
            }
        else:
            event_data = {
                "entry_id": self._entry_id,
                "anticipated_start_time": None,
                "next_schedule_time": None,
                "next_target_temperature": None,
                "anticipation_minutes": None,
                "current_temp": anticipation_data.get("current_temp"),
                "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
                "confidence_level": None,
                "scheduler_entity": None,
            }

        if self._is_meaningful_change_from_last(event_data):
            self._hass.bus.async_fire(
                "intelligent_heating_pilot_anticipation_calculated",
                event_data,
            )
            self._last_published_data = event_data
            _LOGGER.debug("Published anticipation event for sensors (data changed)")
        else:
            _LOGGER.debug(
                "Skipped anticipation event: no meaningful change from last published data"
            )

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
        _LOGGER.debug("Event bridge cleaned up")
