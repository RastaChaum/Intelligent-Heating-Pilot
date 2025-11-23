"""Home Assistant scheduler reader adapter.

This adapter implements ISchedulerReader by reading from Home Assistant
scheduler entities. It translates HA entity states into domain value objects.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.interfaces import ISchedulerReader
from ...domain.value_objects import ScheduleTimeslot
from ..vtherm_compat import get_vtherm_attribute

if TYPE_CHECKING:
    from homeassistant.core import State

_LOGGER = logging.getLogger(__name__)


class HASchedulerReader(ISchedulerReader):
    """Home Assistant implementation of scheduler reader.
    
    Reads scheduled heating timeslots from Home Assistant scheduler entities.
    Supports the scheduler-component data format:
    https://github.com/nielsfaber/scheduler-component/#data-format
    
    This adapter contains NO business logic - it only translates HA states
    to domain value objects.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        scheduler_entity_ids: list[str],
        vtherm_entity_id: str | None = None,
    ) -> None:
        """Initialize the scheduler reader adapter.
        
        Args:
            hass: Home Assistant instance
            scheduler_entity_ids: List of scheduler entity IDs to monitor
            vtherm_entity_id: Optional VTherm climate entity ID used to resolve
                preset temperatures (e.g., when actions use preset modes).
        """
        self._hass = hass
        self._scheduler_entity_ids = scheduler_entity_ids
        self._vtherm_entity_id = vtherm_entity_id
    
    async def get_next_timeslot(self) -> ScheduleTimeslot | None:
        """Retrieve the next scheduled heating timeslot.
        
        Scans all configured scheduler entities and returns the earliest
        upcoming timeslot with a valid time and temperature.
        
        Returns:
            The next schedule timeslot, or None if no valid timeslots found.
        """
        if not self._scheduler_entity_ids:
            _LOGGER.warning("No scheduler entities configured")
            return None
        
        chosen_time: datetime | None = None
        chosen_temp: float | None = None
        chosen_entity: str | None = None
        
        for entity_id in self._scheduler_entity_ids:
            state = self._hass.states.get(entity_id)
            if not state:
                # Use debug level if HA is still starting up, warning otherwise
                if self._hass.is_running:
                    _LOGGER.warning("Scheduler entity not found: %s", entity_id)
                else:
                    _LOGGER.debug("Scheduler entity not yet available (HA starting): %s", entity_id)
                continue
            
            # Skip disabled schedulers (state is "off")
            if state.state == "off":
                _LOGGER.debug("Scheduler %s is disabled (state: off), skipping", entity_id)
                continue
            
            # Extract next trigger time and target temperature
            next_time, target_temp = self._extract_timeslot_data(state)
            
            if next_time and target_temp is not None:
                # Keep track of the earliest timeslot
                if not chosen_time or next_time < chosen_time:
                    chosen_time = next_time
                    chosen_temp = target_temp
                    chosen_entity = entity_id
            else:
                _LOGGER.debug(
                    "Skipped scheduler %s: time=%s temp=%s",
                    entity_id,
                    next_time,
                    target_temp
                )
        
        if chosen_time and chosen_temp is not None and chosen_entity:
            _LOGGER.info(
                "Next timeslot: %s at %s (%.1f°C)",
                chosen_entity,
                chosen_time.strftime("%H:%M"),
                chosen_temp
            )
            return ScheduleTimeslot(
                target_time=chosen_time,
                target_temp=chosen_temp,
                timeslot_id=f"{chosen_entity}_{chosen_time.isoformat()}",
                scheduler_entity=chosen_entity
            )
        
        _LOGGER.debug("No valid scheduler timeslot found (check scheduler configuration and preset temperatures)")
        return None
    
    def _extract_timeslot_data(
        self, state: State
    ) -> tuple[datetime | None, float | None]:
        """Extract next trigger time and target temperature from scheduler state.
        
        Supports multiple scheduler attribute layouts:
        - Standard: next_trigger + next_slot + actions
        - Fallback: next_entries with time and actions
        
        Args:
            state: Home Assistant scheduler entity state
            
        Returns:
            Tuple of (next_time, target_temp), either can be None if not found
        """
        attrs = state.attributes
        
        # Debug logging to understand the actual structure
        _LOGGER.debug(
            "Scheduler %s attributes: next_trigger=%s, next_slot=%s, actions=%s, next_entries=%s",
            state.entity_id,
            attrs.get("next_trigger"),
            attrs.get("next_slot"),
            type(attrs.get("actions")),
            type(attrs.get("next_entries")),
        )
        
        # Try standard format first
        next_time = self._parse_next_trigger(attrs.get("next_trigger"))
        target_temp = self._extract_target_temp_standard(attrs)
        
        # Fallback to next_entries format
        if not next_time or target_temp is None:
            next_time_fallback, target_temp_fallback = self._extract_from_next_entries(attrs)
            if not next_time:
                next_time = next_time_fallback
            if target_temp is None:
                target_temp = target_temp_fallback
        
        return next_time, target_temp
    
    def _parse_next_trigger(self, next_trigger_raw: str | None) -> datetime | None:
        """Parse next_trigger attribute to datetime.
        
        Args:
            next_trigger_raw: Raw next_trigger value from scheduler
            
        Returns:
            Parsed datetime with timezone, or None if parsing fails
        """
        if not next_trigger_raw:
            return None
        
        # Try HA's robust datetime parser first
        parsed = dt_util.parse_datetime(str(next_trigger_raw))
        
        # Fallback to ISO format parsing
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(str(next_trigger_raw))
            except ValueError:
                _LOGGER.debug("Failed to parse next_trigger: %s", next_trigger_raw)
                return None
        
        # Ensure timezone is set
        if parsed and parsed.tzinfo is None:
            parsed = dt_util.as_local(parsed)
        
        return parsed
    
    def _extract_target_temp_standard(self, attrs: dict) -> float | None:
        """Extract target temperature from standard scheduler format.
        
        Uses next_slot index to find the action in the actions list.
        
        Args:
            attrs: Scheduler entity attributes
            
        Returns:
            Target temperature in Celsius, or None if not found
        """
        next_slot = attrs.get("next_slot")
        actions = attrs.get("actions")
        
        if not isinstance(actions, list):
            return None
        
        if not isinstance(next_slot, int) or next_slot < 0 or next_slot >= len(actions):
            return None
        
        action = actions[next_slot]
        return self._extract_temp_from_action(action)
    
    def _extract_from_next_entries(
        self, attrs: dict
    ) -> tuple[datetime | None, float | None]:
        """Extract time and temperature from next_entries fallback format.
        
        Args:
            attrs: Scheduler entity attributes
            
        Returns:
            Tuple of (next_time, target_temp)
        """
        next_entries = attrs.get("next_entries")
        
        if not isinstance(next_entries, list) or not next_entries:
            return None, None
        
        entry = next_entries[0]
        
        # Extract time
        time_raw = entry.get("time") or entry.get("start") or entry.get("trigger_time")
        next_time = self._parse_next_trigger(time_raw) if time_raw else None
        
        # Extract temperature from first action
        entry_actions = entry.get("actions", [])
        target_temp = None
        if isinstance(entry_actions, list) and entry_actions:
            target_temp = self._extract_temp_from_action(entry_actions[0])
        
        return next_time, target_temp
    
    def _extract_temp_from_action(self, action: dict) -> float | None:
        """Extract target temperature from a scheduler action.
        
        Supports:
        - climate.set_temperature with direct temperature value
        - climate.set_preset_mode with preset mapped to temperature
        
        Args:
            action: Scheduler action dictionary
            
        Returns:
            Target temperature in Celsius, or None if not found
        """
        if not isinstance(action, dict):
            return None
        
        service = action.get("service") or action.get("service_call")
        data = action.get("data") or action.get("service_data") or {}
        
        # Direct temperature setting
        if service == "climate.set_temperature":
            temp = data.get("temperature")
            if temp is not None:
                try:
                    return float(temp)
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid temperature in action: %s", temp)
            return None
        
        # Preset mode requires mapping via VTherm attributes
        # This is handled by getting the current VTherm state when the preset is active
        if service == "climate.set_preset_mode":
            preset = (
                data.get("preset_mode")
                or data.get("preset")
                or data.get("mode")
            )
            if isinstance(preset, str):
                # Try resolving using VTherm attributes if available
                resolved = self._resolve_preset_temperature(preset)
                if resolved is not None:
                    return resolved
                _LOGGER.debug(
                    "Could not resolve preset '%s' to temperature (entity=%s)",
                    preset,
                    self._vtherm_entity_id,
                )
            return None
        
        return None

    def is_scheduler_enabled(self, scheduler_entity_id: str) -> bool:
        """Check if a specific scheduler is enabled.
        
        A scheduler is considered enabled if its state is NOT "off".
        This includes states like "on", "idle", "waiting", etc.
        Only the explicit "off" state means the scheduler is disabled.
        
        Args:
            scheduler_entity_id: The scheduler entity ID to check
            
        Returns:
            True if the scheduler is enabled (state != "off"), False otherwise
        """
        state = self._hass.states.get(scheduler_entity_id)
        if not state:
            _LOGGER.debug("Scheduler entity not found when checking state: %s", scheduler_entity_id)
            return False
        
        is_enabled = state.state != "off"
        _LOGGER.debug("Scheduler %s state: %s (enabled: %s)", scheduler_entity_id, state.state, is_enabled)
        return is_enabled
    
    def _resolve_preset_temperature(self, preset: str) -> float | None:
        """Resolve a preset name to a numeric temperature using VTherm attributes.
        
        This uses the VTherm climate entity attributes as the source of truth. It
        attempts common attribute naming conventions, with v8.0.0+ compatibility
        using get_vtherm_attribute() to access both legacy and new data structures.
        
        Args:
            preset: Preset mode name from the scheduler action
        
        Returns:
            Temperature in Celsius, or None if it cannot be resolved.
        """
        if not self._vtherm_entity_id:
            return None
        state = self._hass.states.get(self._vtherm_entity_id)
        if not state:
            _LOGGER.debug("VTherm entity not found: %s", self._vtherm_entity_id)
            return None
        
        key = str(preset).lower().replace(" ", "_")
        
        # First, try the preset_temperatures dict (VTherm v8.0.0+ format)
        preset_temps = get_vtherm_attribute(state, "preset_temperatures")
        if isinstance(preset_temps, dict):
            # VTherm uses format like "eco_temp", "boost_temp", "comfort_temp"
            # Try multiple key patterns
            preset_keys_to_try = [
                f"{key}_temp",           # eco_temp, boost_temp
                f"{key}_temperature",    # eco_temperature
                key,                      # eco, boost (fallback)
                preset.lower(),          # Original lowercase
            ]
            
            for preset_key in preset_keys_to_try:
                if preset_key in preset_temps:
                    try:
                        temp_value = float(preset_temps[preset_key])
                        # Ignore 0 values as they indicate uninitialized presets
                        if temp_value > 0:
                            _LOGGER.debug("Resolved preset '%s' to %.1f°C (from %s)", preset, temp_value, preset_key)
                            return temp_value
                        else:
                            _LOGGER.debug("Skipping preset '%s' with 0°C (likely uninitialized)", preset)
                    except (ValueError, TypeError):
                        _LOGGER.debug("Invalid preset_temperatures value for %s: %s", preset_key, preset_temps[preset_key])
        
        # Fallback: try common naming patterns with v8.0.0+ compatibility
        candidate_keys = [
            f"{key}_temperature",
            f"{key}_temp",
            f"temperature_{key}",
            f"temp_{key}",
        ]
        
        for k in candidate_keys:
            # Use get_vtherm_attribute to handle both legacy and v8.0.0+ formats
            value = get_vtherm_attribute(state, k)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    _LOGGER.debug("Invalid preset attribute %s=%s", k, value)
        
        # Fallback: if this preset is currently active, use current target temperature
        current_preset = get_vtherm_attribute(state, "preset_mode")
        if isinstance(current_preset, str) and current_preset.lower() == key:
            for target_key in ("temperature", "target_temperature", "target_temp"):
                value = get_vtherm_attribute(state, target_key)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass
        
        return None
