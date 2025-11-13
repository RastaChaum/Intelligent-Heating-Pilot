"""The Intelligent Heating Pilot integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ANTICIPATED_START_TIME,
    ATTR_LEARNED_HEATING_SLOPE,
    ATTR_NEXT_SCHEDULE_TIME,
    ATTR_NEXT_TARGET_TEMP,
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_ANTICIPATION_BUFFER,
    DEFAULT_HEATING_SLOPE,
    DOMAIN,
    MAX_ANTICIPATION_TIME,
    MIN_ANTICIPATION_TIME,
    SERVICE_SCHEDULER_RUN_ACTION,
    STORAGE_KEY,
    STORAGE_VERSION,
    VTHERM_ATTR_CURRENT_TEMPERATURE,
    VTHERM_ATTR_SLOPE,
    VTHERM_ATTR_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

class IntelligentHeatingPilotCoordinator:
    """Coordinator for Intelligent Heating Pilot integration."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.config = config_entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{config_entry.entry_id}")
        self._data: dict[str, Any] = {}
        self._cancel_scheduled_start = None
        self._cancel_overshoot_monitor = None
        self._listeners = []
        self._last_scheduled_time = None  # Track last scheduled anticipation to avoid duplicates
        self._last_scheduled_lhs = None  # Track LHS used for last schedule
        self._anticipation_trigger_executed: set[datetime] = set()  # Track executed triggers
        self._is_updating = False  # Prevent concurrent updates
        self._ignore_vtherm_changes_until: datetime | None = None  # Ignore VTherm changes during our own modifications

    async def async_load(self) -> None:
        """Load stored data."""
        stored_data = await self._store.async_load()
        if stored_data:
            self._data = stored_data
            _LOGGER.debug("Loaded stored data: %s", self._data)
        else:
            self._data = {
                "historical_slopes": [],  # Historical slopes from VTherm (positive=heating, negative=cooling)
                "learned_heating_slope": DEFAULT_HEATING_SLOPE,
            }

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save(self._data)

    def get_vtherm_entity(self) -> str:
        """Get VTherm entity ID (options override data)."""
        return (
            self.config.options.get(CONF_VTHERM_ENTITY)
            if isinstance(self.config.options, dict) and self.config.options.get(CONF_VTHERM_ENTITY) is not None
            else self.config.data.get(CONF_VTHERM_ENTITY)
        )

    def get_scheduler_entities(self) -> list[str]:
        """Get scheduler entity IDs (options override data)."""
        return (
            self.config.options.get(CONF_SCHEDULER_ENTITIES)
            if isinstance(self.config.options, dict) and self.config.options.get(CONF_SCHEDULER_ENTITIES) is not None
            else self.config.data
        )

    def get_humidity_in_entity(self) -> str | None:
        """Get indoor humidity entity ID (options override data)."""
        return (
            self.config.options.get(CONF_HUMIDITY_IN_ENTITY)
            if isinstance(self.config.options, dict) and self.config.options.get(CONF_HUMIDITY_IN_ENTITY) is not None
            else self.config.data.get(CONF_HUMIDITY_IN_ENTITY)
        )

    def get_humidity_out_entity(self) -> str | None:
        """Get outdoor humidity entity ID (options override data)."""
        return (
            self.config.options.get(CONF_HUMIDITY_OUT_ENTITY)
            if isinstance(self.config.options, dict) and self.config.options.get(CONF_HUMIDITY_OUT_ENTITY) is not None
            else self.config.data.get(CONF_HUMIDITY_OUT_ENTITY)
        )

    def get_cloud_cover_entity(self) -> str | None:
        """Get cloud cover entity ID (options override data)."""
        return (
            self.config.options.get(CONF_CLOUD_COVER_ENTITY)
            if isinstance(self.config.options, dict) and self.config.options.get(CONF_CLOUD_COVER_ENTITY) is not None
            else self.config.data.get(CONF_CLOUD_COVER_ENTITY)
        )

    def get_vtherm_slope(self) -> float:
        """Get current slope from VTherm entity and update learning history (options-aware)."""
        entity_id = self.get_vtherm_entity()
        if not entity_id:
            _LOGGER.warning("VTherm entity id missing for slope -> using default slope %s", DEFAULT_HEATING_SLOPE)
            return DEFAULT_HEATING_SLOPE
        vtherm_state = self.hass.states.get(entity_id)
        if not vtherm_state:
            _LOGGER.warning("VTherm entity not found: %s -> using default slope %s", entity_id, DEFAULT_HEATING_SLOPE)
            return DEFAULT_HEATING_SLOPE

        # DEBUG: Log ALL attributes to find the correct slope attribute
        _LOGGER.debug("VTherm %s ALL attributes: %s", entity_id, vtherm_state.attributes)

        # Try to get slope from VTherm attributes
        slope = vtherm_state.attributes.get(VTHERM_ATTR_SLOPE)
        _LOGGER.debug("VTherm %s slope attribute (%s): %s (type: %s)", entity_id, VTHERM_ATTR_SLOPE, slope, type(slope).__name__)
        
        if slope is not None:
            try:
                slope_value = float(slope)
                _LOGGER.debug("Parsed slope value: %.4f°C/h (original: %s)", slope_value, slope)
                
                # Only learn from positive slopes (heating phase)
                # Negative slopes indicate cooling, which we don't want to learn from
                if slope_value > 0:
                    _LOGGER.debug("Positive slope detected, updating learning history")
                    self._update_learned_slope(slope_value)
                else:
                    _LOGGER.debug("Negative slope (%.4f°C/h), skipping learning (cooling phase)", slope_value)
                
                return abs(slope_value)  # Return absolute value for current calculations
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid slope value from VTherm: %s", slope)
        else:
            _LOGGER.warning("No slope attribute found in VTherm %s", entity_id)

        fallback = self._data.get("max_heating_slope", DEFAULT_HEATING_SLOPE)
        _LOGGER.debug("Using fallback slope: %.2f°C/h", fallback)
        return fallback

    def _update_learned_slope(self, slope: float) -> None:
        """Update learned slopes history."""
        # Accept all slope values (positive = heating, negative = cooling)
        slopes = self._data.get("historical_slopes", [])
        old_lhs = self._data.get("learned_heating_slope")
        
        slopes.append(slope)

        # Keep only last 100 values (~30 days if updated a few times per day)
        if len(slopes) > 100:
            slopes = slopes[-100:]

        self._data["historical_slopes"] = slopes

        # Calculate robust average (trimmed mean) for LHS
        lhs = self._calculate_robust_average(slopes)
        self._data["learned_heating_slope"] = lhs
        _LOGGER.debug("Updated learned heating slope: %.2f°C/h (from %d samples)", lhs, len(slopes))

        # If LHS changed significantly (>0.1°C/h), trigger anticipation recalculation
        if old_lhs is not None and abs(lhs - old_lhs) > 0.1:
            _LOGGER.info("LHS changed significantly from %.2f to %.2f°C/h, triggering anticipation recalculation", 
                        old_lhs, lhs)
            self.hass.async_create_task(self.async_update())

        # Save asynchronously
        self.hass.async_create_task(self.async_save())

    def _calculate_robust_average(self, values: list[float]) -> float:
        """Calculate robust average by removing extreme values (trimmed mean)."""
        if not values:
            return DEFAULT_HEATING_SLOPE

        # Sort values
        sorted_values = sorted(values)
        n = len(sorted_values)

        if n < 4:
            # Not enough data for trimming, use simple average
            return sum(sorted_values) / n

        # Remove top and bottom 10% (trimmed mean)
        trim_count = max(1, int(n * 0.1))
        trimmed = sorted_values[trim_count:-trim_count]

        if not trimmed:
            # Fallback to median if trimming removed everything
            return sorted_values[n // 2]

        return sum(trimmed) / len(trimmed)

    def get_learned_heating_slope(self) -> float:
        """Get the learned heating slope (LHS)."""
        slopes = self._data.get("historical_slopes", [])
        
        # Filter out negative slopes (cooling phases) - only keep positive heating slopes
        positive_slopes = [s for s in slopes if s > 0]
        
        if not positive_slopes:
            _LOGGER.debug("No positive learned slopes in history, using default: %.2f°C/h", DEFAULT_HEATING_SLOPE)
            return DEFAULT_HEATING_SLOPE

        # Return calculated LHS (robust average), or recalculate if missing
        lhs = self._data.get("learned_heating_slope")
        if lhs is None or lhs <= 0:
            # Recalculate using only positive slopes
            lhs = self._calculate_robust_average(positive_slopes)
            self._data["learned_heating_slope"] = lhs
            _LOGGER.debug("Recalculated LHS from %d positive samples: %.2f°C/h", len(positive_slopes), lhs)
        else:
            _LOGGER.debug("Using cached LHS: %.2f°C/h (from %d positive samples)", lhs, len(positive_slopes))

        return lhs

    def get_historical_slopes(self) -> list[float]:
        """Get the list of learned slopes for public access."""
        return self._data.get("historical_slopes", [])

    def get_vtherm_current_temp(self) -> float | None:
        """Get current temperature from VTherm (options-aware)."""
        entity_id = self.get_vtherm_entity()
        if not entity_id:
            _LOGGER.debug("VTherm entity id missing for current temp")
            return None
        vtherm_state = self.hass.states.get(entity_id)
        if not vtherm_state:
            _LOGGER.debug("VTherm state not found for %s", entity_id)
            return None

        temp = vtherm_state.attributes.get(VTHERM_ATTR_CURRENT_TEMPERATURE)
        if temp is not None:
            try:
                return float(temp)
            except (ValueError, TypeError):
                pass
        return None

    def get_next_scheduler_event(self) -> tuple[datetime | None, float | None, str | None]:
        """
        Get next scheduler event details.
        
        Returns:
            Tuple of (next_schedule_time, next_target_temp, scheduler_entity_id)
        """
        scheduler_entities = self.get_scheduler_entities()
        chosen_time: datetime | None = None
        chosen_temp: float | None = None
        chosen_scheduler: str | None = None

        for entity_id in scheduler_entities:
            state = self.hass.states.get(entity_id)
            if not state:
                continue

            attrs = state.attributes
            _LOGGER.debug("Scheduler %s attributes: %s", entity_id, attrs)

            # Primary source: next_trigger + next_slot + actions
            next_trigger_raw = attrs.get("next_trigger")
            next_slot = attrs.get("next_slot")
            actions = attrs.get("actions")

            next_time: datetime | None = None
            if next_trigger_raw:
                # Use Home Assistant datetime parser first (preserves timezone)
                next_time = dt_util.parse_datetime(str(next_trigger_raw))
                if next_time is None:
                    try:
                        parsed = datetime.fromisoformat(str(next_trigger_raw))
                        # Ensure timezone is set to local if naive
                        next_time = dt_util.as_local(parsed) if parsed.tzinfo is None else parsed
                    except ValueError:
                        _LOGGER.warning("Unable to parse next_trigger '%s' for %s", next_trigger_raw, entity_id)

            target_temp: float | None = None
            if isinstance(actions, list) and isinstance(next_slot, int) and 0 <= next_slot < len(actions):
                action = actions[next_slot]
                target_temp = self._extract_target_temp_from_action(action)
            else:
                # Fallback: some versions expose next_entries list
                next_entries = attrs.get("next_entries")
                if isinstance(next_entries, list) and next_entries:
                    entry = next_entries[0]
                    entry_actions = entry.get("actions", [])
                    if isinstance(entry_actions, list) and entry_actions:
                        target_temp = self._extract_target_temp_from_action(entry_actions[0])
                    entry_time = entry.get("time") or entry.get("start") or entry.get("trigger_time")
                    if entry_time and not next_time:
                        parsed = dt_util.parse_datetime(str(entry_time))
                        if parsed is None:
                            parsed = self._safe_fromiso(str(entry_time))
                            # Ensure local timezone if naive
                            if parsed and parsed.tzinfo is None:
                                parsed = dt_util.as_local(parsed)
                        next_time = parsed

            if next_time and target_temp is not None:
                # Choose earliest upcoming among all scheduler entities
                if not chosen_time or next_time < chosen_time:
                    chosen_time = next_time
                    chosen_temp = target_temp
                    chosen_scheduler = entity_id

        if chosen_time:
            _LOGGER.debug(
                "Selected next scheduler event: %s at %s target %.2f°C", chosen_scheduler, chosen_time, chosen_temp
            )
        else:
            _LOGGER.debug("No valid scheduler event found among %s", scheduler_entities)

        return chosen_time, chosen_temp, chosen_scheduler

    def _safe_fromiso(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _extract_target_temp_from_action(self, action: dict) -> float | None:
        """Derive target temperature from a scheduler action.

        Supports:
        - climate.set_temperature {temperature: X}
        - climate.set_preset_mode {preset_mode: name} -> mapped to a temperature using VTherm attributes.
        """
        if not isinstance(action, dict):
            return None
        service = action.get("service") or action.get("service_call")
        data = action.get("data") or action.get("service_data") or {}

        # Direct temperature
        if service == "climate.set_temperature":
            temp = data.get("temperature")
            try:
                return float(temp) if temp is not None else None
            except (ValueError, TypeError):
                return None

        # Preset mode mapping
        if service == "climate.set_preset_mode":
            preset = data.get("preset_mode") or data.get("preset")
            if preset:
                vtherm_state = self.hass.states.get(self.get_vtherm_entity())
                if not vtherm_state:
                    return None
                # 1. Try explicit attribute naming convention: <preset>_temperature or <preset>_temp
                for key, val in vtherm_state.attributes.items():
                    if not isinstance(val, (int, float, str)):
                        continue
                    if preset in key and ("temp" in key or "temperature" in key):
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            continue
                # 2. If current preset equals requested preset, use its current target temperature
                current_preset = vtherm_state.attributes.get("preset_mode")
                if current_preset == preset:
                    current_target = vtherm_state.attributes.get("temperature") or vtherm_state.attributes.get("target_temp")
                    try:
                        return float(current_target) if current_target is not None else None
                    except (ValueError, TypeError):
                        pass
                # 3. Fallback: generic temperature attribute
                fallback = vtherm_state.attributes.get("temperature") or vtherm_state.attributes.get("target_temp")
                try:
                    return float(fallback) if fallback is not None else None
                except (ValueError, TypeError):
                    return None
        return None

    async def async_calculate_anticipation(
        self,
        next_time: datetime | None = None,
        next_temp: float | None = None,
        scheduler_entity: str | None = None
    ) -> dict[str, Any] | None:
        """Calculate anticipation time for next schedule.
        
        Args:
            next_time: Next schedule time (if not provided, will be fetched)
            next_temp: Next target temperature (if not provided, will be fetched)
            scheduler_entity: Scheduler entity ID (if not provided, will be fetched)
        """
        # Get next scheduler event if not provided
        if next_time is None or next_temp is None:
            next_time, next_temp, scheduler_entity = self.get_next_scheduler_event()

        if not next_time or not next_temp:
            _LOGGER.debug("No next schedule event found")
            return None

        # Get current temperature
        current_temp = self.get_vtherm_current_temp()
        if current_temp is None:
            _LOGGER.warning("Cannot get current temperature from VTherm")
            return None

        # Get learned heating slope
        lhs = self.get_learned_heating_slope()

        # Calculate base anticipation time
        temp_delta = next_temp - current_temp

        if temp_delta <= 0:
            _LOGGER.debug("Target temp (%.1f°C) <= current temp (%.1f°C), no heating needed", 
                         next_temp, current_temp)
            # Return anticipation data = next_time to indicate no anticipation needed
            return {
                ATTR_NEXT_SCHEDULE_TIME: next_time,
                ATTR_NEXT_TARGET_TEMP: next_temp,
                ATTR_ANTICIPATED_START_TIME: next_time,
                "anticipation_minutes": 0,
                "current_temp": current_temp,
                "scheduler_entity": scheduler_entity,
                ATTR_LEARNED_HEATING_SLOPE: lhs,
            }

        # Protection against division by zero
        if lhs <= 0:
            _LOGGER.warning("Invalid LHS (%.4f°C/h), cannot calculate anticipation. Using default.", lhs)
            lhs = DEFAULT_HEATING_SLOPE

        # Anticipation = (Target - Current) / (LHS / 60)
        anticipation_minutes = (temp_delta / lhs) * 60.0

        # Apply correction factors based on optional sensors
        correction_factor = 1.0

        # Humidity correction
        humidity_in = self._get_sensor_value(self.get_humidity_in_entity())
        if humidity_in and humidity_in > 70:
            correction_factor *= 1.1  # High humidity = slower heating

        # Cloud coverage correction (less sun = slower heating)
        cloud_cover = self._get_sensor_value(self.get_cloud_cover_entity())
        if cloud_cover and cloud_cover > 80:
            correction_factor *= 1.05

        anticipation_minutes *= correction_factor

        # Apply buffer and limits
        anticipation_minutes += DEFAULT_ANTICIPATION_BUFFER
        anticipation_minutes = max(MIN_ANTICIPATION_TIME, min(MAX_ANTICIPATION_TIME, anticipation_minutes))

        # Calculate anticipated start time, preserving timezone
        anticipated_start = next_time - timedelta(minutes=anticipation_minutes)
        
        # Ensure timezone is preserved (convert naive to local if needed)
        if anticipated_start.tzinfo is None:
            anticipated_start = dt_util.as_local(anticipated_start)
        if next_time.tzinfo is None:
            next_time = dt_util.as_local(next_time)

        result = {
            ATTR_NEXT_SCHEDULE_TIME: next_time,
            ATTR_NEXT_TARGET_TEMP: next_temp,
            ATTR_ANTICIPATED_START_TIME: anticipated_start,
            "anticipation_minutes": anticipation_minutes,
            "current_temp": current_temp,
            "scheduler_entity": scheduler_entity,
            ATTR_LEARNED_HEATING_SLOPE: lhs,
        }

        _LOGGER.info(
            "Anticipation calculated: Start at %s (%.1f min before %s) for target %.1f°C (current: %.1f°C, LHS: %.2f°C/h)",
            anticipated_start.isoformat(),
            anticipation_minutes,
            next_time.isoformat(),
            next_temp,
            current_temp,
            lhs,
        )

        return result

    def _get_sensor_value(self, entity_id: str | None) -> float | None:
        """Get sensor value safely."""
        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if not state:
            return None

        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _is_vtherm_already_at_target(self, target_temp: float, tolerance: float = 0.2) -> bool:
        """Check if VTherm is already configured for the target temperature.

        Returns True if:
        - VTherm's target temperature is already set to target_temp (within tolerance)
        - VTherm is heating (hvac_mode = heat or hvac_action = heating)

        This indicates the scheduler was already triggered and we shouldn't re-trigger.
        """
        vtherm_state = self.hass.states.get(self.get_vtherm_entity())
        if not vtherm_state:
            return False

        attrs = vtherm_state.attributes

        # Check target temperature
        current_target = attrs.get("temperature") or attrs.get(VTHERM_ATTR_TEMPERATURE)
        if current_target is None:
            return False

        try:
            current_target_float = float(current_target)
            # Must be heating actively OR hvac_mode == heat; ignore auto unless actively heating
            hvac_mode = vtherm_state.state
            hvac_action = attrs.get("hvac_action")
            actively_heating = hvac_action == "heating" or hvac_mode == "heat"
            if actively_heating and abs(current_target_float - target_temp) <= tolerance:
                _LOGGER.debug(
                    "VTherm already at target (%.2f≈%.2f, mode=%s action=%s) -> skip scheduling",
                    current_target_float,
                    target_temp,
                    hvac_mode,
                    hvac_action,
                )
                return True
        
        except (ValueError, TypeError):
            # If the target temperature is not a valid float, treat as not already at target
            return False

        return False

    async def async_schedule_anticipation(self, anticipation_data: dict) -> None:
        """Schedule the anticipated start."""
        anticipated_start = anticipation_data[ATTR_ANTICIPATED_START_TIME]
        scheduler_entity = anticipation_data["scheduler_entity"]
        next_schedule_time = anticipation_data[ATTR_NEXT_SCHEDULE_TIME]
        lhs = anticipation_data.get(ATTR_LEARNED_HEATING_SLOPE, 0)
        now = dt_util.now()

        # Check if this is a "no anticipation needed" marker (midnight 1970)
        if anticipated_start == next_schedule_time:
            _LOGGER.debug("No anticipation needed (target temp <= current temp), skipping scheduling")
            # Cancel any existing scheduled start
            if self._cancel_scheduled_start:
                self._cancel_scheduled_start()
                self._cancel_scheduled_start = None
            self._last_scheduled_time = None
            self._last_scheduled_lhs = None
            return

        _LOGGER.info("Scheduling anticipation: start=%s, target_time=%s, LHS=%.2f°C/h", 
                    anticipated_start.isoformat(), next_schedule_time.isoformat(), lhs)

        # Check if we already scheduled this anticipation with same LHS (avoid duplicates)
        # BUT allow rescheduling if LHS changed significantly
        if self._last_scheduled_time == anticipated_start and self._last_scheduled_lhs is not None:
            if abs(lhs - self._last_scheduled_lhs) < 0.05:  # Less than 0.05°C/h change
                _LOGGER.debug(
                    "Already scheduled anticipation for %s with similar LHS (%.2f vs %.2f), skipping duplicate",
                    anticipated_start.isoformat(), self._last_scheduled_lhs, lhs
                )
                return
            else:
                _LOGGER.info(
                    "Rescheduling anticipation for %s due to LHS change (%.2f -> %.2f°C/h)",
                    anticipated_start.isoformat(), self._last_scheduled_lhs, lhs
                )

        # Cancel any existing scheduled start
        if self._cancel_scheduled_start:
            self._cancel_scheduled_start()
            self._cancel_scheduled_start = None

        # Mark this time and LHS as scheduled
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs

        # If anticipated start is in the past BUT next_schedule_time is in the future,
        # trigger immediately (handles restarts, delays, etc.)
        if anticipated_start <= now < next_schedule_time:

            _LOGGER.info(
                "Anticipated start time %s is past but next schedule %s is future. Triggering scheduler action immediately.",
                anticipated_start.isoformat(),
                next_schedule_time.isoformat()
            )
            
            # Ignore VTherm state changes for the next 10 seconds (scheduler will modify it)
            self._ignore_vtherm_changes_until = dt_util.now() + timedelta(seconds=10)
            
            # Trigger scheduler action with time format (HH:MM)
            trigger_time = next_schedule_time.strftime("%H:%M")
            await self.hass.services.async_call(
                "scheduler",
                SERVICE_SCHEDULER_RUN_ACTION,
                {
                    "entity_id": scheduler_entity,
                    "time": trigger_time,
                    "skip_conditions": False
                },
                blocking=True,
            )
            
            # Start overshoot monitoring
            await self.async_start_overshoot_monitoring(anticipation_data)
            
            # Reset the last scheduled time
            self._last_scheduled_time = None
            return

        # If anticipated start is in the past AND next_schedule is also past, skip
        if anticipated_start <= now and next_schedule_time <= now:
            _LOGGER.debug(
                "Both anticipated start %s and next schedule %s are in the past, skipping",
                anticipated_start.isoformat(),
                next_schedule_time.isoformat()
            )
            self._last_scheduled_time = None
            return

        # Normal case: schedule for future time
        @callback
        def trigger_scheduler_action(_now):
            """Trigger scheduler action at anticipated start time."""
            async def trigger_async():
                """Async wrapper for scheduler action."""
                _LOGGER.info(
                    "Triggering anticipated start: running scheduler %s action",
                    scheduler_entity
                )
                _LOGGER.debug(
                    "Scheduling details: now=%s anticipated_start=%s next_schedule=%s",
                    dt_util.now().isoformat(),
                    anticipated_start.isoformat(),
                    next_schedule_time.isoformat(),
                )
                
                # Ignore VTherm state changes for the next 10 seconds (scheduler will modify it)
                self._ignore_vtherm_changes_until = dt_util.now() + timedelta(seconds=10)
                
                # Trigger scheduler action with time format (HH:MM)
                trigger_time = next_schedule_time.strftime("%H:%M")
                await self.hass.services.async_call(
                    "scheduler",
                    SERVICE_SCHEDULER_RUN_ACTION,
                    {
                        "entity_id": scheduler_entity,
                        "time": trigger_time,
                        "skip_conditions": False
                    },
                    blocking=True,
                )

                # Start overshoot monitoring
                await self.async_start_overshoot_monitoring(anticipation_data)
                
                # Reset the last scheduled time after execution
                self._last_scheduled_time = None
            
            self.hass.async_create_task(trigger_async())

        self._cancel_scheduled_start = async_track_point_in_time(
            self.hass, trigger_scheduler_action, anticipated_start
        )

        _LOGGER.info("Scheduled anticipation trigger at %s for next schedule at %s", 
                     anticipated_start.isoformat(), next_schedule_time.isoformat())

    async def async_start_overshoot_monitoring(self, anticipation_data: dict[str, Any]) -> None:
        """Start monitoring for overshoot after anticipated start."""
        next_schedule_time = anticipation_data[ATTR_NEXT_SCHEDULE_TIME]
        next_target_temp = anticipation_data[ATTR_NEXT_TARGET_TEMP]

        async def check_overshoot():
            """Check if we're overshooting the target."""
            # Check if we've passed the schedule time
            if dt_util.now() >= next_schedule_time:
                _LOGGER.debug("Schedule time reached, stopping overshoot monitoring")
                if self._cancel_overshoot_monitor:
                    self._cancel_overshoot_monitor()
                    self._cancel_overshoot_monitor = None
                return False  # Stop monitoring

            current_temp = self.get_vtherm_current_temp()
            if current_temp is None:
                return True  # Continue monitoring

            current_slope = self.get_vtherm_slope()
            time_to_schedule = (next_schedule_time - dt_util.now()).total_seconds() / 60.0

            # Estimate if we'll overshoot
            estimated_temp_at_schedule = current_temp + (current_slope * time_to_schedule / 60.0)

            # If we're going to overshoot by more than 0.5°C, turn off heating
            if estimated_temp_at_schedule > next_target_temp + 0.5:
                _LOGGER.warning(
                    "Overshoot detected! Current: %.1f°C, estimated at schedule: %.1f°C, target: %.1f°C. Turning off heating.",
                    current_temp,
                    estimated_temp_at_schedule,
                    next_target_temp,
                )

                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {
                        "entity_id": self.get_vtherm_entity(),
                        "hvac_mode": "off",
                    },
                    blocking=True,
                )

                # Cancel monitoring after turning off
                if self._cancel_overshoot_monitor:
                    self._cancel_overshoot_monitor()
                    self._cancel_overshoot_monitor = None
                return False  # Stop monitoring

            return True  # Continue monitoring

        # Monitor every 2 minutes until schedule time
        @callback
        def schedule_next_check(_now=None):
            """Schedule next overshoot check."""
            async def check_and_maybe_reschedule():
                """Check overshoot and reschedule if needed."""
                should_continue = await check_overshoot()
                if should_continue:
                    # Re-arm the timed callback in 2 minutes
                    self._cancel_overshoot_monitor = async_track_point_in_time(
                        self.hass,
                        schedule_next_check,
                        dt_util.now() + timedelta(minutes=2),
                    )
            
            self.hass.async_create_task(check_and_maybe_reschedule())

        # Start the monitoring loop with the first arm
        self._cancel_overshoot_monitor = async_track_point_in_time(
            self.hass,
            schedule_next_check,
            dt_util.now() + timedelta(minutes=2),
        )

    async def async_update(self) -> None:
        """Update calculation and schedule."""
        # Prevent concurrent updates (debounce)
        if self._is_updating:
            _LOGGER.debug("Update already in progress, skipping")
            return
        
        self._is_updating = True
        try:
            await self._async_update_internal()
        finally:
            self._is_updating = False
    
    async def _async_update_internal(self) -> None:
        """Internal update logic."""
        # Always fetch next schedule info first
        next_time, next_temp, scheduler_entity = self.get_next_scheduler_event()
        # Refresh live VTherm metrics so sensors can reflect latest values
        current_temp = self.get_vtherm_current_temp()
        # Sample current slope to keep learning history updated
        _ = self.get_vtherm_slope()
        # Check if VTherm is already at the target temperature
        # This means the scheduler was already triggered, avoid re-triggering
        skip_schedule = False
        if next_temp is not None and self._is_vtherm_already_at_target(next_temp):
            _LOGGER.debug(
                "VTherm already at target temperature (%.1f°C), will skip anticipation scheduling only",
                next_temp
            )
            skip_schedule = True
        _LOGGER.debug(
            "Update snapshot: next_time=%s next_temp=%s scheduler=%s current_temp=%s skip_schedule=%s",
            getattr(next_time, 'isoformat', lambda: None)() if next_time is not None else None,
            next_temp,
            scheduler_entity,
            current_temp,
            skip_schedule,
        )

        # Try to calculate anticipation (pass already-fetched scheduler info to avoid duplicate calls)
        anticipation_data = await self.async_calculate_anticipation(next_time, next_temp, scheduler_entity)

        # If we have full anticipation and not skipping, schedule it
        if anticipation_data and not skip_schedule:
            await self.async_schedule_anticipation(anticipation_data)
        elif anticipation_data and skip_schedule:
            # Fallback: if anticipated start already passed and not executed, force trigger
            anticipated_start = anticipation_data[ATTR_ANTICIPATED_START_TIME]
            if isinstance(anticipated_start, datetime):
                now = dt_util.now()
                if anticipated_start <= now < next_time and anticipated_start not in self._anticipation_trigger_executed:
                    _LOGGER.debug(
                        "Forcing immediate scheduler action despite skip (target matched but heating inactive)."
                    )
                    try:
                        # Ignore VTherm state changes for the next 10 seconds (scheduler will modify it)
                        self._ignore_vtherm_changes_until = dt_util.now() + timedelta(seconds=10)
                        
                        # Trigger scheduler action with time format (HH:MM)
                        trigger_time = next_time.strftime("%H:%M")
                        await self.hass.services.async_call(
                            "scheduler",
                            SERVICE_SCHEDULER_RUN_ACTION,
                            {
                                "entity_id": scheduler_entity,
                                "time": trigger_time,
                                "skip_conditions": False
                            },
                            blocking=True,
                        )
                        self._anticipation_trigger_executed.add(anticipated_start)
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning("Forced scheduler trigger failed: %s", err, exc_info=True)

        # Build payload for sensors, always emitting at least next schedule info
        payload: dict[str, Any] = {"entry_id": self.config.entry_id}
        if next_time is not None:
            payload[ATTR_NEXT_SCHEDULE_TIME] = next_time.isoformat()
        if next_temp is not None:
            payload[ATTR_NEXT_TARGET_TEMP] = next_temp
        if scheduler_entity is not None:
            payload["scheduler_entity"] = scheduler_entity
        if current_temp is not None:
            payload["current_temp"] = current_temp
        payload[ATTR_LEARNED_HEATING_SLOPE] = self.get_learned_heating_slope()

        if anticipation_data:
            # Merge anticipated data; ensure datetimes are ISO strings for event bus
            payload.update(
                {
                    ATTR_ANTICIPATED_START_TIME: anticipation_data[ATTR_ANTICIPATED_START_TIME].isoformat(),
                    "anticipation_minutes": anticipation_data.get("anticipation_minutes"),
                    "current_temp": anticipation_data.get("current_temp"),
                    ATTR_LEARNED_HEATING_SLOPE: anticipation_data.get(ATTR_LEARNED_HEATING_SLOPE),
                }
            )

        # Fire event for sensors even if partial data
        self.hass.bus.async_fire(
            f"{DOMAIN}_anticipation_calculated",
            payload,
        )

    async def async_cleanup(self) -> None:
        """Cleanup scheduled tasks."""
        if self._cancel_scheduled_start:
            self._cancel_scheduled_start()
            self._cancel_scheduled_start = None

        if self._cancel_overshoot_monitor:
            self._cancel_overshoot_monitor()
            self._cancel_overshoot_monitor = None
        
        # Reset tracking
        self._last_scheduled_time = None

        for unsub in self._listeners:
            unsub()
        self._listeners.clear()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Intelligent Heating Pilot component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intelligent Heating Pilot from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create coordinator
    coordinator = IntelligentHeatingPilotCoordinator(hass, entry)
    await coordinator.async_load()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # (Legacy global state_changed_listener removed – using filtered tracking below)

    # Replace global EVENT_STATE_CHANGED listen with filtered tracking limited to this entry's entities
    tracked_entities: list[str] = []
    vtherm = coordinator.get_vtherm_entity()
    if vtherm:
        tracked_entities.append(vtherm)
    tracked_entities.extend(coordinator.get_scheduler_entities())
    for extra in [coordinator.get_humidity_in_entity(), coordinator.get_humidity_out_entity(), coordinator.get_cloud_cover_entity()]:
        if extra:
            tracked_entities.append(extra)

    @callback
    def _filtered_state_change(event: Event):
        entity_id = event.data.get("entity_id")
        if entity_id not in tracked_entities:
            return
        # Dedicated logic for VTherm attribute-based triggering
        if vtherm and entity_id == vtherm:
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if old_state and new_state:
                old_ema = old_state.attributes.get(VTHERM_ATTR_CURRENT_TEMPERATURE)
                new_ema = new_state.attributes.get(VTHERM_ATTR_CURRENT_TEMPERATURE)
                old_slope = old_state.attributes.get(VTHERM_ATTR_SLOPE)
                new_slope = new_state.attributes.get(VTHERM_ATTR_SLOPE)
                ema_changed = old_ema != new_ema
                slope_changed = old_slope != new_slope
                if ema_changed or slope_changed:
                    if coordinator._ignore_vtherm_changes_until and dt_util.now() < coordinator._ignore_vtherm_changes_until:
                        _LOGGER.debug("[%s] Ignoring self-induced VTherm change", entry.entry_id)
                        return
                    if ema_changed:
                        _LOGGER.debug("[%s] VTherm ema_temp %s -> %s", entry.entry_id, old_ema, new_ema)
                    if slope_changed:
                        _LOGGER.debug("[%s] VTherm slope %s -> %s", entry.entry_id, old_slope, new_slope)
                    hass.async_create_task(coordinator.async_update())
                return
        # Any change on other tracked entities triggers update
        _LOGGER.debug("[%s] Tracked entity %s changed -> update", entry.entry_id, entity_id)
        hass.async_create_task(coordinator.async_update())

    if tracked_entities:
        unsub = async_track_state_change_event(hass, tracked_entities, _filtered_state_change)
        coordinator._listeners.append(unsub)
        _LOGGER.debug("[%s] Tracking entities: %s", entry.entry_id, tracked_entities)
    else:
        _LOGGER.warning("[%s] No entities to track", entry.entry_id)

    # Do initial update
    await coordinator.async_update()

    # Also run again right after HA finished starting (some entities may appear only then)
    @callback
    def _ha_started(_event):
        _LOGGER.debug("Home Assistant started event received, re-running initial update for %s", entry.entry_id)
        hass.async_create_task(coordinator.async_update())

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _ha_started)

    # And a small delayed update to catch late attribute population (e.g., next_trigger)
    @callback
    def _delayed_initial(_now):
        _LOGGER.debug("Running delayed initial update for %s", entry.entry_id)
        hass.async_create_task(coordinator.async_update())

    cancel_delayed = async_track_point_in_time(
        hass, _delayed_initial, dt_util.now() + timedelta(seconds=30)
    )
    coordinator._listeners.append(cancel_delayed)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register services
    async def handle_reset_learning(call):
        """Handle the reset_learning service call."""
        _LOGGER.info("Resetting learning history")
        coordinator._data["historical_slopes"] = []
        coordinator._data["learned_heating_slope"] = None
        await coordinator.async_save()
        _LOGGER.info("Learning history cleared, will use default heating slope until new data is collected")

    hass.services.async_register(DOMAIN, "reset_learning", handle_reset_learning)

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Get coordinator and cleanup
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_cleanup()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
