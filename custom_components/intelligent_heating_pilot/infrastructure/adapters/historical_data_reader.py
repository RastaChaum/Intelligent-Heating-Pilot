"""Home Assistant Historical Data Reader Adapter.

This adapter implements IHistoricalDataReader to extract heating cycles
and historical sensor data from the Home Assistant recorder database.

Supports SQLite, PostgreSQL, and MariaDB/MySQL backends.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import recorder
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from ..vtherm_compat import get_vtherm_attribute

from ...domain.interfaces.historical_data_reader import IHistoricalDataReader
from ...domain.value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)

# Constants for scheduler time matching
SCHEDULER_QUERY_WINDOW_HOURS = 23  # How far back to look for scheduler states
SCHEDULER_MATCH_TOLERANCE_SECONDS = 10800  # 3 hours tolerance for matching scheduled times


class HAHistoricalDataReader(IHistoricalDataReader):
    """Home Assistant implementation of IHistoricalDataReader.
    
    Extracts historical data from HA recorder database (SQLite/PostgreSQL/MariaDB).
    Uses the recorder component's history API for efficient queries.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        scheduler_entity_ids: list[str] | None = None,
    ) -> None:
        """Initialize the historical data reader.
        
        Args:
            hass: Home Assistant instance with recorder integration.
            scheduler_entity_ids: List of scheduler entity IDs to query for scheduled times.
        """
        self._hass = hass
        self._scheduler_entity_ids = scheduler_entity_ids or []
        
    async def get_heating_cycles(
        self,
        climate_entity_id: str,
        start_date: datetime,
        end_date: datetime,
        humidity_entity_id: str | None = None,
        outdoor_temp_entity_id: str | None = None,
        outdoor_humidity_entity_id: str | None = None,
        cloud_coverage_entity_id: str | None = None,
    ) -> list[HeatingCycle]:
        """Extract and reconstruct heating cycles from HA database.
        
        A heating cycle is detected when:
        1. Thermostat is in "heat" mode
        2. Room temperature is at least 0.3°C below target temperature
        
        The cycle ends when either condition is no longer met.
        This approach is scheduler-independent and focuses on actual heating behavior.
        
        Args:
            climate_entity_id: Entity ID of the climate/thermostat
            start_date: Start of extraction period
            end_date: End of extraction period
            humidity_entity_id: Optional indoor humidity sensor entity
            outdoor_temp_entity_id: Optional outdoor temperature sensor entity
            outdoor_humidity_entity_id: Optional outdoor humidity sensor entity
            cloud_coverage_entity_id: Optional cloud coverage sensor entity
            
        Returns:
            List of reconstructed HeatingCycle objects with environmental data.
        """
        _LOGGER.debug(
            "Extracting heating cycles for %s from %s to %s",
            climate_entity_id,
            start_date,
            end_date,
        )
        
        # Get climate entity history
        states = await self._get_entity_states(
            climate_entity_id,
            start_date,
            end_date,
        )
        
        if not states:
            _LOGGER.warning("No historical states found for %s", climate_entity_id)
            return []
        
        # Reconstruct cycles from state changes chronologically
        cycles = []
        current_cycle_start: datetime | None = None
        current_cycle_initial_temp: float | None = None
        current_cycle_target_temp: float | None = None
        
        for state in states:
            hvac_mode = state.state
            current_temp = self._safe_float(get_vtherm_attribute(state, "current_temperature"))
            target_temp = self._safe_float(get_vtherm_attribute(state, "temperature"))
            
            # Check if cycle conditions are met
            is_heating = hvac_mode == "heat"
            has_temp_delta = (current_temp is not None and target_temp is not None and 
                            (target_temp - current_temp) >= 0.3)
            
            # Detect cycle start
            if is_heating and has_temp_delta and current_cycle_start is None:
                current_cycle_start = state.last_changed
                current_cycle_initial_temp = current_temp
                current_cycle_target_temp = target_temp
                delta_temp = current_cycle_target_temp - current_cycle_initial_temp if current_cycle_initial_temp is not None and current_cycle_target_temp is not None else 0.0
                _LOGGER.debug(
                    "Cycle started at %s (initial: %.1f°C, target: %.1f°C, delta: %.1f°C)",
                    current_cycle_start,
                    current_cycle_initial_temp,
                    current_cycle_target_temp,
                    delta_temp,
                )
            
            # Detect cycle end: conditions no longer met
            elif current_cycle_start is not None and (not is_heating or not has_temp_delta):
                cycle_end = state.last_changed
                final_temp = current_temp if current_temp is not None else current_cycle_target_temp
                
                # Calculate duration
                duration_minutes = (cycle_end - current_cycle_start).total_seconds() / 60.0
                
                # Skip very short cycles (likely noise)
                if duration_minutes < 5.0:
                    _LOGGER.debug("Skipping very short cycle (%.1f min)", duration_minutes)
                    current_cycle_start = None
                    current_cycle_initial_temp = None
                    current_cycle_target_temp = None
                    continue
                
                # Get environmental data at cycle start
                initial_slope = await self._get_slope_at_time(climate_entity_id, current_cycle_start)
                initial_humidity = await self._get_humidity_at_time(humidity_entity_id, current_cycle_start) if humidity_entity_id else None
                initial_outdoor_temp = await self._get_outdoor_temp_at_time(outdoor_temp_entity_id, current_cycle_start) if outdoor_temp_entity_id else None
                initial_outdoor_humidity = await self._get_outdoor_humidity_at_time(outdoor_humidity_entity_id, current_cycle_start) if outdoor_humidity_entity_id else None
                initial_cloud_coverage = await self._get_cloud_coverage_at_time(cloud_coverage_entity_id, current_cycle_start) if cloud_coverage_entity_id else None
                
                # Get environmental data at cycle end
                final_slope = await self._get_slope_at_time(climate_entity_id, cycle_end)
                final_humidity = await self._get_humidity_at_time(humidity_entity_id, cycle_end) if humidity_entity_id else None
                final_outdoor_temp = await self._get_outdoor_temp_at_time(outdoor_temp_entity_id, cycle_end) if outdoor_temp_entity_id else None
                final_outdoor_humidity = await self._get_outdoor_humidity_at_time(outdoor_humidity_entity_id, cycle_end) if outdoor_humidity_entity_id else None
                final_cloud_coverage = await self._get_cloud_coverage_at_time(cloud_coverage_entity_id, cycle_end) if cloud_coverage_entity_id else None
                
                cycle = HeatingCycle(
                    climate_entity_id=climate_entity_id,
                    cycle_start=current_cycle_start,
                    cycle_end=cycle_end,
                    duration_minutes=duration_minutes,
                    initial_temp=current_cycle_initial_temp if current_cycle_initial_temp is not None else 0.0,
                    target_temp=current_cycle_target_temp if current_cycle_target_temp is not None else 0.0,
                    final_temp=final_temp if final_temp is not None else 0.0,
                    initial_slope=initial_slope,
                    final_slope=final_slope,
                    initial_humidity=initial_humidity,
                    final_humidity=final_humidity,
                    initial_outdoor_temp=initial_outdoor_temp,
                    initial_outdoor_humidity=initial_outdoor_humidity,
                    initial_cloud_coverage=initial_cloud_coverage,
                    final_outdoor_temp=final_outdoor_temp,
                    final_outdoor_humidity=final_outdoor_humidity,
                    final_cloud_coverage=final_cloud_coverage,
                )
                cycles.append(cycle)
                _LOGGER.debug(
                    "Cycle completed: %s (duration: %.1f min, temp: %.1f→%.1f°C)",
                    cycle.cycle_id,
                    duration_minutes,
                    current_cycle_initial_temp,
                    final_temp,
                )
                
                # Reset for next cycle
                current_cycle_start = None
                current_cycle_initial_temp = None
                current_cycle_target_temp = None

        _LOGGER.info("Extracted %d heating cycles for %s", len(cycles), climate_entity_id)
        return cycles
    
    async def get_room_humidity_history(
        self,
        humidity_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical humidity data from HA recorder."""
        return await self._get_numeric_history(
            humidity_entity_id,
            start_time,
            end_time,
            resolution_minutes,
        )
    
    async def get_room_temperature_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical temperature data from climate entity."""
        states = await self._get_entity_states(climate_entity_id, start_time, end_time)
        
        history_data = []
        for state in states:
            temp = self._safe_float(get_vtherm_attribute(state, "current_temperature"))
            if temp is not None:
                history_data.append((state.last_changed, temp))
        
        # Apply resolution sampling if needed
        if resolution_minutes > 0 and history_data:
            history_data = self._resample_history(history_data, resolution_minutes)
        
        return history_data
    
    async def get_radiator_power_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve radiator power history from climate entity.
        
        For VersatileThermostat/other thermostats, power is typically represented
        as a percentage (0-100) in a sensor attribute or related power sensor.
        """
        # Try to get power from climate entity attributes first
        states = await self._get_entity_states(climate_entity_id, start_time, end_time)
        
        history_data = []
        for state in states:
            # Check common power attribute names
            power = None
            for attr in ["power_percent", "valve_position", "heating_power"]:
                power = self._safe_float(get_vtherm_attribute(state, attr))
                if power is not None:
                    break
            
            # If no power attribute, infer from HVAC mode (0 or 100)
            if power is None:
                power = 100.0 if state.state == "heat" else 0.0
            
            history_data.append((state.last_changed, power))
        
        # Apply resolution sampling
        if resolution_minutes > 0 and history_data:
            history_data = self._resample_history(history_data, resolution_minutes)
        
        return history_data
    
    async def get_room_slopes_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve learned heating slopes from IHP storage.
        
        Note: This queries a custom sensor that stores learned slopes.
        Entity ID pattern: sensor.ihp_{climate_entity}_learned_slope
        """
        """Retrieve historical temperature data from climate entity."""
        states = await self._get_entity_states(climate_entity_id, start_time, end_time)
        
        history_data = []
        for state in states:
            temp = self._safe_float(get_vtherm_attribute(state, "temperature_slope"))
            if temp is not None:
                history_data.append((state.last_changed, temp))
        
        # Apply resolution sampling if needed
        if resolution_minutes > 0 and history_data:
            history_data = self._resample_history(history_data, resolution_minutes)
        
        return history_data
    
    async def get_cloud_coverage_history(
        self,
        cloud_coverage_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 15,
    ) -> list[tuple[datetime, float]]:
        """Retrieve cloud coverage history from weather entity."""
        return await self._get_numeric_history(
            cloud_coverage_entity_id,
            start_time,
            end_time,
            resolution_minutes,
        )
    
    async def get_outdoor_temperature_history(
        self,
        outdoor_temperature_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 15,
    ) -> list[tuple[datetime, float]]:
        """Retrieve outdoor temperature history."""
        return await self._get_numeric_history(
            outdoor_temperature_entity_id,
            start_time,
            end_time,
            resolution_minutes,
        )
    
    # Private helper methods
    
    async def _get_entity_states(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[State]:
        """Get historical states for an entity from recorder.
        
        Args:
            entity_id: Entity to query
            start_time: Start of period
            end_time: End of period
            
        Returns:
            List of State objects ordered by timestamp.
        """
        # Ensure we're in executor context for DB queries
        def _get_states():
            return history.state_changes_during_period(
                self._hass,
                start_time,
                end_time,
                entity_id,
                no_attributes=False,
                descending=False,
            ).get(entity_id, [])
        
        try:
            states = await recorder.get_instance(self._hass).async_add_executor_job(_get_states)
            return states
        except Exception as e:
            _LOGGER.error("Failed to get states for %s: %s", entity_id, e)
            return []
    
    async def _get_numeric_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int,
    ) -> list[tuple[datetime, float]]:
        """Generic method to get numeric sensor history.
        
        Args:
            entity_id: Sensor entity ID
            start_time: Start of period
            end_time: End of period
            resolution_minutes: Sampling resolution
            
        Returns:
            List of (timestamp, value) tuples.
        """
        states = await self._get_entity_states(entity_id, start_time, end_time)
        
        history_data = []
        for state in states:
            value = self._safe_float(state.state)
            if value is not None:
                history_data.append((state.last_changed, value))
        
        # Apply resolution sampling
        if resolution_minutes > 0 and history_data:
            history_data = self._resample_history(history_data, resolution_minutes)
        
        return history_data
       
    async def _get_slope_at_time(self, climate_entity_id: str, timestamp: datetime) -> float | None:
        """Get learned slope at specific time.
        
        Queries a small window around the timestamp (±1 minute) to account for
        slight timing differences in state updates.
        """
        states = await self._get_entity_states(climate_entity_id, timestamp - timedelta(minutes=1), timestamp + timedelta(minutes=1))
        for state in states:
            temp = self._safe_float(get_vtherm_attribute(state, "temperature_slope"))
            if temp is not None:
                return temp
            
        return None
    
    async def _get_humidity_at_time(self, humidity_entity_id: str | None, timestamp: datetime) -> float | None:
        """Get humidity at specific time."""
        if not humidity_entity_id:
            return None
        states = await self._get_entity_states(humidity_entity_id, timestamp - timedelta(minutes=1), timestamp + timedelta(minutes=1))
        for state in states:
            value = self._safe_float(state.state)
            if value is not None:
                return value
        return None
    
    async def _get_outdoor_temp_at_time(self, outdoor_temp_entity_id: str | None, timestamp: datetime) -> float | None:
        """Get outdoor temperature at specific time."""
        if not outdoor_temp_entity_id:
            return None
        states = await self._get_entity_states(outdoor_temp_entity_id, timestamp - timedelta(minutes=1), timestamp + timedelta(minutes=1))
        for state in states:
            value = self._safe_float(state.state)
            if value is not None:
                return value
        return None
    
    async def _get_outdoor_humidity_at_time(self, outdoor_humidity_entity_id: str | None, timestamp: datetime) -> float | None:
        """Get outdoor humidity at specific time."""
        if not outdoor_humidity_entity_id:
            return None
        states = await self._get_entity_states(outdoor_humidity_entity_id, timestamp - timedelta(minutes=1), timestamp + timedelta(minutes=1))
        for state in states:
            value = self._safe_float(state.state)
            if value is not None:
                return value
        return None
    
    async def _get_cloud_coverage_at_time(self, cloud_coverage_entity_id: str | None, timestamp: datetime) -> float | None:
        """Get cloud coverage at specific time."""
        if not cloud_coverage_entity_id:
            return None
        states = await self._get_entity_states(cloud_coverage_entity_id, timestamp - timedelta(minutes=1), timestamp + timedelta(minutes=1))
        for state in states:
            value = self._safe_float(state.state)
            if value is not None:
                return value
        return None
    
    async def _get_scheduled_target_time(
        self,
        cycle_start: datetime,
        cycle_end: datetime,
    ) -> datetime | None:
        """Get the scheduled target time from scheduler entity history.
        
        Queries scheduler entities to find what time was scheduled to reach
        the target temperature during this heating cycle.
        
        Args:
            cycle_start: When heating started
            cycle_end: When heating ended
            
        Returns:
            The scheduled target time, or None if not found.
        """
        if not self._scheduler_entity_ids:
            _LOGGER.debug("No scheduler entities configured for historical lookup")
            return None
        
        for entity_id in self._scheduler_entity_ids:
            states = await self._get_entity_states(entity_id, cycle_start - timedelta(minutes=15), cycle_end + timedelta(hours=3))
            
            if not states:
                _LOGGER.debug("No scheduler history found for %s", entity_id)
                continue
            
            # Look for scheduler state with next_trigger around cycle_end time
            for state in states:
                next_trigger = self._parse_next_trigger(state.attributes.get("next_trigger"))
                
                if next_trigger:
                    # Ensure both datetimes have timezone info for comparison
                    cycle_end_aware = cycle_end if cycle_end.tzinfo else dt_util.as_local(cycle_end)
                    
                    # Check if this scheduled time is within reasonable range of cycle
                    # The schedule should be between cycle_start and a reasonable time after cycle_end
                    time_diff = abs((next_trigger - cycle_end_aware).total_seconds())
                    
                    # If next_trigger is close to cycle_end, this is likely our schedule
                    if time_diff <= SCHEDULER_MATCH_TOLERANCE_SECONDS:
                        _LOGGER.debug(
                            "Found scheduled time %s from %s (diff: %.1f min for cycle %s to %s)",
                            next_trigger,
                            entity_id,
                            time_diff / 60.0,
                            cycle_start,
                            cycle_end,
                        )
                        return next_trigger
        
        _LOGGER.debug("No matching scheduled time found for cycle %s to %s", cycle_start, cycle_end)
        return None
    
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
    
    async def _find_target_reached_time(
        self,
        states: list[State],
        target_temp: float,
        tolerance: float = 0.3,
    ) -> datetime | None:
        """Find when target temperature was first reached in state history.
        
        Args:
            states: List of states to search (ordered chronologically)
            target_temp: Target temperature to find
            tolerance: Acceptable temperature difference (±°C)
            
        Returns:
            Timestamp when target was reached, or None if never reached.
        """
        for state in states:
            current_temp = self._safe_float(get_vtherm_attribute(state, "current_temperature"))
            if current_temp is not None and abs(current_temp - target_temp) <= tolerance:
                return state.last_changed
            
        return None
        
    def _resample_history(
        self,
        history_data: list[tuple[datetime, float]],
        resolution_minutes: int,
    ) -> list[tuple[datetime, float]]:
        """Downsample history data to specified resolution.
        
        Takes the average of values within each resolution window.
        
        Args:
            history_data: Original data points
            resolution_minutes: Target resolution in minutes
            
        Returns:
            Resampled data at lower resolution.
        """
        if not history_data or resolution_minutes <= 0:
            return history_data
        
        resampled = []
        resolution_delta = timedelta(minutes=resolution_minutes)
        
        current_window_start = history_data[0][0]
        window_values = []
        
        for timestamp, value in history_data:
            if timestamp >= current_window_start + resolution_delta:
                # Close current window
                if window_values:
                    avg_value = sum(window_values) / len(window_values)
                    resampled.append((current_window_start, avg_value))
                
                # Start new window
                current_window_start = current_window_start + resolution_delta
                window_values = []
            
            window_values.append(value)
        
        # Close final window
        if window_values:
            avg_value = sum(window_values) / len(window_values)
            resampled.append((current_window_start, avg_value))
        
        return resampled
    
    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Safely convert value to float, returning None on failure."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
