"""Application service - orchestrates domain and infrastructure.

This service coordinates between the domain layer (HeatingPilot, PredictionService)
and infrastructure adapters, implementing use cases.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..domain.entities import HeatingPilot
from ..domain.services import PredictionService
from ..domain.value_objects import HeatingAction, HeatingDecision, SlopeData

if TYPE_CHECKING:
    from ..infrastructure.adapters import (
        HAClimateCommander,
        HAEnvironmentReader,
        HAModelStorage,
        HASchedulerCommander,
        HASchedulerReader,
    )

_LOGGER = logging.getLogger(__name__)


class HeatingApplicationService:
    """Application service orchestrating heating control use cases.
    
    This service is the main entry point for heating logic, coordinating:
    - Domain aggregates (HeatingPilot)
    - Domain services (PredictionService)
    - Infrastructure adapters (HA*)
    
    NO Home Assistant dependencies - only uses adapter interfaces.
    """
    
    def __init__(
        self,
        scheduler_reader: "HASchedulerReader",
        model_storage: "HAModelStorage",
        scheduler_commander: "HASchedulerCommander",
        climate_commander: "HAClimateCommander",
        environment_reader: "HAEnvironmentReader",
        lhs_window_hours: float = 6.0,
    ) -> None:
        """Initialize the application service.
        
        Args:
            scheduler_reader: Reads scheduled timeslots
            model_storage: Persists learned slopes
            scheduler_commander: Triggers scheduler actions
            climate_commander: Controls climate entity
            environment_reader: Reads environmental conditions
            lhs_window_hours: Time window in hours for contextual LHS (default: 6)
        """
        self._scheduler_reader = scheduler_reader
        self._model_storage = model_storage
        self._scheduler_commander = scheduler_commander
        self._climate_commander = climate_commander
        self._environment_reader = environment_reader
        self._prediction_service = PredictionService()
        self._lhs_window_hours = lhs_window_hours
        
        # Runtime state for anticipation scheduling
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
    
    async def process_slope_update(self, new_slope: float) -> None:
        """Process a new slope value from VTherm.
        
        Only learns positive slopes when heating is active.
        
        Args:
            new_slope: New slope value in °C/h
        """
        # Only learn if heating is active and slope is positive
        if not self._environment_reader.is_heating_active():
            _LOGGER.debug("Heating not active, skipping slope learning")
            return
        
        if new_slope <= 0:
            _LOGGER.debug("Negative slope %.2f°C/h, skipping (cooling phase)", new_slope)
            return
        
        # Create timestamped slope data
        slope_data = SlopeData(
            slope_value=new_slope,
            timestamp=dt_util.now()
        )
        
        # Learn the slope via adapter
        old_lhs = await self._model_storage.get_learned_heating_slope()
        await self._model_storage.save_slope_data(slope_data)
        new_lhs = await self._model_storage.get_learned_heating_slope()
        
        # Log significant changes
        if old_lhs is not None and abs(new_lhs - old_lhs) > 0.1:
            _LOGGER.info(
                "LHS changed significantly from %.2f to %.2f°C/h",
                old_lhs,
                new_lhs
            )
    
    async def _get_contextual_lhs(self, target_time: datetime) -> float:
        """Get LHS from time window preceding target time.
        
        Args:
            target_time: Target schedule time
            
        Returns:
            LHS calculated from time-windowed slopes, or global LHS as fallback
        """
        # Get slopes from time window before target time
        window_slopes = await self._model_storage.get_slopes_in_time_window(
            before_time=target_time,
            window_hours=self._lhs_window_hours
        )
        
        if not window_slopes:
            # Fallback to global LHS
            global_lhs = await self._model_storage.get_learned_heating_slope()
            _LOGGER.warning(
                "No slopes in time window (%.1f hours before %s), using global LHS: %.2f°C/h",
                self._lhs_window_hours,
                target_time.isoformat(),
                global_lhs
            )
            return global_lhs
        
        # Calculate robust average from window slopes
        slope_values = [sd.slope_value for sd in window_slopes]
        
        # Use same trimmed mean algorithm as storage adapter
        sorted_values = sorted(slope_values)
        n = len(sorted_values)
        
        if n < 4:
            # Not enough data for trimming, use simple average
            contextual_lhs = sum(sorted_values) / n
        else:
            # Remove top and bottom 10% (trimmed mean)
            trim_count = max(1, int(n * 0.1))
            trimmed = sorted_values[trim_count:-trim_count]
            contextual_lhs = sum(trimmed) / len(trimmed) if trimmed else sorted_values[n // 2]
        
        _LOGGER.debug(
            "Calculated contextual LHS from %d slopes in %.1fh window: %.2f°C/h",
            len(window_slopes),
            self._lhs_window_hours,
            contextual_lhs
        )
        
        return contextual_lhs
    
    async def calculate_and_schedule_anticipation(self) -> dict | None:
        """Calculate anticipation and schedule heating start.
        
        Returns:
            Dict with anticipation data for sensors, or None if not applicable
        """
        # Get next timeslot
        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            _LOGGER.debug("No scheduled timeslot found")
            return None
        
        # Get current environment
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            _LOGGER.warning("Cannot read current environment")
            return None
              
        # Get contextual LHS from time window preceding target time
        lhs = await self._get_contextual_lhs(timeslot.target_time)
        
        # Check if already at target
        if environment.current_temp >= timeslot.target_temp:
            _LOGGER.debug(
                "Already at target (%.1f°C >= %.1f°C)",
                environment.current_temp,
                timeslot.target_temp
            )
            return {
                "anticipated_start_time": timeslot.target_time,
                "next_schedule_time": timeslot.target_time,
                "next_target_temp": timeslot.target_temp,
                "anticipation_minutes": 0,
                "current_temp": environment.current_temp,
                "learned_heating_slope": lhs,
                "confidence_level": 100,
                "timeslot_id": timeslot.timeslot_id,
            }

        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.current_temp,
            target_temp=timeslot.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.humidity,
            learned_slope=lhs,
            target_time=timeslot.target_time,
            cloud_coverage=environment.cloud_coverage,
        )
        
        _LOGGER.info(
            "Anticipation: start at %s (%.1f min) for target %.1f°C at %s (LHS: %.2f°C/h, confidence: %.2f)",
            prediction.anticipated_start_time.isoformat(),
            prediction.estimated_duration_minutes,
            timeslot.target_temp,
            timeslot.target_time.isoformat(),
            prediction.learned_heating_slope,
            prediction.confidence_level,
        )
        
        # Schedule if needed
        await self._schedule_anticipation(
            anticipated_start=prediction.anticipated_start_time,
            target_time=timeslot.target_time,
            target_temp=timeslot.target_temp,
            lhs=prediction.learned_heating_slope,
        )
        
        # Return data for sensors
        return {
            "anticipated_start_time": prediction.anticipated_start_time,
            "next_schedule_time": timeslot.target_time,
            "next_target_temp": timeslot.target_temp,
            "anticipation_minutes": prediction.estimated_duration_minutes,
            "current_temp": environment.current_temp,
            "learned_heating_slope": prediction.learned_heating_slope,
            "confidence_level": prediction.confidence_level,
            "timeslot_id": timeslot.timeslot_id,
        }
    
    async def _schedule_anticipation(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        lhs: float,
    ) -> None:
        """Schedule anticipated heating start.
        
        Args:
            anticipated_start: When to start heating
            target_time: Target schedule time
            lhs: Learned heating slope used
        """
        now = dt_util.now()
        
        # Check for duplicate scheduling
        if (
            self._last_scheduled_time == anticipated_start
            and self._last_scheduled_lhs is not None
            and abs(lhs - self._last_scheduled_lhs) < 0.05
        ):
            _LOGGER.debug("Already scheduled this anticipation, skipping duplicate")
            return
        
        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs
        
        # If anticipated start is in past but target is future, trigger now
        if anticipated_start <= now < target_time:
            _LOGGER.info(
                "Anticipated start %s is past, triggering immediately",
                anticipated_start.isoformat()
            )
            await self._scheduler_commander.run_action(target_time)
            # Safety: Force HVAC to heat with the intended target temperature
            # Some setups may switch HVAC mode to 'off' despite preset being applied.
            try:
                await self._climate_commander.turn_on_heat(target_temp)
            except Exception:
                _LOGGER.warning("Failed to force HVAC heat after scheduler action", exc_info=True)
            return
        
        # If both are in past, skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are past, skipping")
            return
        
        # Schedule for future (would need a task scheduler in real implementation)
        _LOGGER.info(
            "Would schedule anticipation at %s for target %s",
            anticipated_start.isoformat(),
            target_time.isoformat()
        )
        # TODO: Implement actual scheduling mechanism
    
    async def check_overshoot_risk(self) -> None:
        """Check if heating should stop to prevent overshoot."""
        # Get next timeslot
        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            return
        
        # Get current environment and slope
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            return
        
        current_slope = self._environment_reader.get_vtherm_slope()
        if current_slope is None or current_slope <= 0:
            return
        
        # Calculate estimated temperature at target time
        now = dt_util.now()
        if now >= timeslot.target_time:
            return
        
        time_to_target = (timeslot.target_time - now).total_seconds() / 3600.0
        estimated_temp = environment.current_temp + (current_slope * time_to_target)
        
        # Check overshoot threshold
        overshoot_threshold = timeslot.target_temp + 0.5
        
        if estimated_temp > overshoot_threshold:
            _LOGGER.warning(
                "Overshoot risk! Current: %.1f°C, estimated: %.1f°C, target: %.1f°C - turning off",
                environment.current_temp,
                estimated_temp,
                timeslot.target_temp
            )
            await self._climate_commander.turn_off()
    
    async def reset_learned_slopes(self) -> None:
        """Reset all learned slope history."""
        _LOGGER.info("Resetting learned heating slope history")
        await self._model_storage.clear_slope_history()
