"""Home Assistant event bridge - translates HA events to orchestrator calls.

This infrastructure component listens to HA entity state changes and delegates
to the orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .adapters.utils import (
    WEATHER_ATTR_CLOUD_COVERAGE,
    WEATHER_ATTR_HUMIDITY,
    WEATHER_DOMAIN,
    read_numeric_state,
)
from .vtherm_compat import get_vtherm_room_temperature

if TYPE_CHECKING:
    from datetime import datetime

    from ..application import HeatingOrchestrator

_LOGGER = logging.getLogger(__name__)

# Minimum change in monitored sensor value (humidity %, cloud coverage %) to
# trigger a recalculation.  Small fluctuations below this threshold are ignored.
_MONITORED_ENTITY_CHANGE_THRESHOLD = 3.0
# Weather attributes the prediction reads live. The outdoor temperature is left
# out: the prediction does not use it, so its changes cannot alter the result
# (#227), even when one weather entity also backs humidity or cloud coverage.
_MONITORED_WEATHER_ATTRIBUTES = (WEATHER_ATTR_HUMIDITY, WEATHER_ATTR_CLOUD_COVERAGE)
# Key used for the value of a sensor, whose number is its state.
_SENSOR_STATE_KEY = "state"

# Tolerance in seconds for anticipated_start_time comparison.  Changes smaller
# than this are not considered meaningful enough to re-publish the event.
_ANTICIPATION_TIME_TOLERANCE_SECONDS = 60
# Tolerances below which a numeric field change is not worth re-publishing.
_CURRENT_TEMP_TOLERANCE = 0.1
_LHS_TOLERANCE = 0.05
# Confidence is a 0-1 ratio: one percentage point is the smallest visible step.
_CONFIDENCE_TOLERANCE = 0.01


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

        # Track all entities that should trigger updates. One weather entity may back
        # several fields: track it once, otherwise each of its updates would fire the
        # listener (and a recalculation) once per field.
        self._tracked_entities = list(
            dict.fromkeys([vtherm_entity_id] + scheduler_entity_ids + self._monitored_entity_ids)
        )

        # Listener cleanup callbacks
        self._listeners: list = []

        # Debouncing state
        self._ignore_vtherm_until: datetime | None = None

        # Deduplication: remember the last event data that was published so we
        # can skip firing when nothing meaningful has changed.
        self._last_published_data: dict | None = None
        # Set when sensors must re-read the coordinator even if the anticipation
        # itself did not change (e.g. after a learning reset).
        self._force_next_publish = False

        # Monitored values last acted on, per (entity_id, value key). Comparing to
        # these rather than to the previous state lets a slow drift add up.
        self._monitored_references: dict[tuple[str, str], float] = {}

        # Track active tasks for proper shutdown
        self._active_tasks: set = set()
        self._is_shutting_down = False
        self._recalculate_task: asyncio.Task | None = None
        self._recalculate_pending = False

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
        if meaningful and not self._is_shutting_down:
            _LOGGER.debug("Entity %s changed meaningfully, triggering update", entity_id)
            self._request_recalculate()
        elif not meaningful:
            _LOGGER.debug("Entity %s change not actionable, skipping recalculation", entity_id)

    def request_forced_publish(self) -> None:
        """Recalculate and publish the next event even if nothing changed.

        Sensors such as the LHS ones read their value from the coordinator and
        only refresh on this event, so after a learning reset the event must
        not be dropped as a duplicate.
        """
        self._force_next_publish = True
        self._request_recalculate()

    def _request_recalculate(self) -> None:
        """Request a recalculation with coalescing.

        If a recalculation is already running, mark one pending pass instead of
        spawning additional concurrent tasks.
        """
        if self._is_shutting_down:
            return

        if self._recalculate_task is not None and not self._recalculate_task.done():
            self._recalculate_pending = True
            _LOGGER.debug("Recalculation already running, coalescing trigger")
            return

        task = self._hass.async_create_task(self._run_recalculate_loop())
        self._recalculate_task = task
        self._active_tasks.add(task)
        task.add_done_callback(self._on_recalculate_task_done)

    def _on_recalculate_task_done(self, task: asyncio.Task) -> None:
        """Track recalculation task completion and cleanup references."""
        self._active_tasks.discard(task)
        if self._recalculate_task is task:
            self._recalculate_task = None

    async def _run_recalculate_loop(self) -> None:
        """Run recalculation and process one coalesced pending request if needed."""
        while not self._is_shutting_down:
            try:
                await self._recalculate_and_publish()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Error during recalculation workflow: %s", exc, exc_info=True)

            if self._recalculate_pending:
                self._recalculate_pending = False
                _LOGGER.debug("Processing coalesced recalculation trigger")
                continue
            break

    def _has_meaningful_scheduler_change(self, event: Event[EventStateChangedData]) -> bool:
        """Return True only when a scheduler state change is actionable for IHP.

        Ignores attribute-only updates that do not affect the IHP schedule
        (e.g., internal counters, last_triggered, etc.).  Only the following
        changes are considered meaningful:

        - The enabled / disabled state (on / off) toggled.
        - The ``next_trigger`` timestamp changed (different upcoming slot).
        - The ``next_event`` timestamp changed (native ``schedule.*`` entities,
          e.g. tomorrow's ON time moved while the schedule is off).
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

        if old_attrs.get("next_event") != new_attrs.get("next_event"):
            return True

        # Target temperature / actions changed
        return bool(old_attrs.get("actions") != new_attrs.get("actions"))

    def _has_meaningful_monitored_change(self, event: Event[EventStateChangedData]) -> bool:
        """Return True only when a monitored value moved significantly.

        Values are compared to the last value acted on, so tiny fluctuations are
        ignored while a slow drift still triggers once it adds up. Availability
        transitions are always considered meaningful.
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

        new_values = self._monitored_values(new_state)
        if not new_values and new_state.domain != WEATHER_DOMAIN:
            # Non-numeric sensor: trigger on any state string change
            return bool(old_state.state != new_state.state)

        entity_id = new_state.entity_id
        old_values = self._monitored_values(old_state)
        meaningful = False
        for key in new_values.keys() | old_values.keys():
            reference_key = (entity_id, key)
            if reference_key not in self._monitored_references and key in old_values:
                # First sighting: the previous value is the baseline the drift adds to
                self._monitored_references[reference_key] = old_values[key]
            reference = self._monitored_references.get(reference_key)
            new_val = new_values.get(key)
            if reference is None or new_val is None:
                # Value appearing or disappearing is actionable
                meaningful = meaningful or reference is not new_val
                continue
            if abs(new_val - reference) >= _MONITORED_ENTITY_CHANGE_THRESHOLD:
                meaningful = True

        if meaningful:
            # A recalculation reads every value, so they all become the new reference
            for key in old_values.keys() - new_values.keys():
                self._monitored_references.pop((entity_id, key), None)
            for key, value in new_values.items():
                self._monitored_references[(entity_id, key)] = value
        return meaningful

    @staticmethod
    def _monitored_values(state: State) -> dict[str, float]:
        """Return the numeric values carried by a monitored entity state.

        A weather state is a condition string that IHP does not use, so only the
        numeric attributes the prediction reads count. A sensor carries its
        value in the state.
        """
        if state.domain == WEATHER_DOMAIN:
            keys: tuple[str, ...] = _MONITORED_WEATHER_ATTRIBUTES
        else:
            keys = (_SENSOR_STATE_KEY,)
        values = {}
        for key in keys:
            value = read_numeric_state(state, key)
            if value is not None:
                values[key] = value
        return values

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

        numeric_tolerances = (
            ("current_temp", _CURRENT_TEMP_TOLERANCE),
            ("learned_heating_slope", _LHS_TOLERANCE),
            ("confidence_level", _CONFIDENCE_TOLERANCE),
        )
        for key, tolerance in numeric_tolerances:
            if self._numeric_changed(new_data.get(key), last.get(key), tolerance):
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

    @staticmethod
    def _numeric_changed(new: float | None, last: float | None, tolerance: float) -> bool:
        """Return True when a numeric field moved by at least *tolerance*.

        A transition between "no data" and a real value is always a change.
        """
        if (new is None) != (last is None):
            return True
        return new is not None and last is not None and abs(new - last) >= tolerance

    def _handle_vtherm_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle VTherm state changes (temperature filter + recalculation trigger).

        Args:
            event: State change event
        """
        if self._is_shutting_down:
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not old_state or not new_state:
            return

        # Check if we should ignore (self-induced change)
        if self._ignore_vtherm_until and dt_util.now() < self._ignore_vtherm_until:
            _LOGGER.debug("Ignoring self-induced VTherm change")
            return

        # Same room temperature as the anticipation reads: a raw reading toggling
        # while the smoothed one stays put must not move the pending preheat (#258).
        old_temp = get_vtherm_room_temperature(old_state)
        new_temp = get_vtherm_room_temperature(new_state)

        if old_temp == new_temp:
            _LOGGER.debug("VTherm change but temperature unchanged, skipping")
            return

        _LOGGER.debug("VTherm temperature changed: %s -> %s", old_temp, new_temp)
        self._request_recalculate()

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
                "humidity": anticipation_data.get("humidity"),
                "cloud_coverage": anticipation_data.get("cloud_coverage"),
                "scheduler_blocked": anticipation_data.get("scheduler_blocked", False),
                "blocked_schedulers": anticipation_data.get("blocked_schedulers", []),
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
                "humidity": anticipation_data.get("humidity"),
                "cloud_coverage": anticipation_data.get("cloud_coverage"),
                "scheduler_blocked": anticipation_data.get("scheduler_blocked", False),
                "blocked_schedulers": anticipation_data.get("blocked_schedulers", []),
            }

        if self._force_next_publish or self._is_meaningful_change_from_last(event_data):
            self._force_next_publish = False
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

    async def async_cleanup(self) -> None:
        """Cleanup all event listeners and cancel pending tasks.

        This is called during integration unload to ensure:
        1. No more events trigger new calculations
        2. All pending tasks are cancelled with timeout
        """
        _LOGGER.debug("Starting event bridge cleanup with %d active tasks", len(self._active_tasks))
        self._is_shutting_down = True

        # Unsubscribe from all listeners to prevent new tasks
        for unsub in self._listeners:
            unsub()
        self._listeners.clear()

        # Cancel all active tasks with timeout
        if self._active_tasks:
            _LOGGER.debug("Cancelling %d active recalculation tasks", len(self._active_tasks))
            for task in self._active_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete (with timeout to prevent hangs)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=5.0,  # 5-second timeout for all tasks
                )
            except TimeoutError:
                _LOGGER.warning(
                    "Timeout waiting for %d tasks to shutdown; forcing cleanup",
                    len(self._active_tasks),
                )
            finally:
                self._active_tasks.clear()

        _LOGGER.debug("Event bridge cleanup completed")

    def cleanup(self) -> None:
        """Synchronous cleanup for backwards compatibility.

        Note: This is called by code that doesn't support async, but doesn't
        cancel pending tasks. Use async_cleanup() during normal unload.
        """
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        for unsub in self._listeners:
            unsub()
        self._listeners.clear()
        _LOGGER.debug("Event bridge cleaned up (sync mode)")
