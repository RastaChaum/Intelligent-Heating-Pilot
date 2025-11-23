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
from ..domain.services import PredictionService, LHSCalculationService
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
        self._lhs_calculation_service = LHSCalculationService()
        self._lhs_window_hours = lhs_window_hours
        
        # Runtime state for anticipation scheduling
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._is_preheating_active: bool = False
        self._preheating_target_time: datetime | None = None
        self._active_scheduler_entity: str | None = None  # Track which scheduler is being used
    
    def _clear_anticipation_state(self) -> None:
        """Clear all anticipation tracking state."""
        self._is_preheating_active = False
        self._preheating_target_time = None
        self._last_scheduled_time = None
        self._last_scheduled_lhs = None
        self._active_scheduler_entity = None
        _LOGGER.debug("Anticipation state cleared")
    
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
        # Get all slope data from storage
        all_slope_data = await self._model_storage.get_all_slope_data()
        
        if not all_slope_data:
            # Fallback to global LHS if no data available
            global_lhs = await self._model_storage.get_learned_heating_slope()
            _LOGGER.warning(
                "No slope data available, using global LHS: %.2f°C/h",
                global_lhs
            )
            return global_lhs
        
        # Use domain service to calculate contextual LHS based on time window
        # Domain service handles the filtering and calculation logic
        contextual_lhs = self._lhs_calculation_service.calculate_contextual_lhs(
            all_slope_data=all_slope_data,
            target_time=target_time,
            window_hours=self._lhs_window_hours
        )
        
        # If domain service returns default (no slopes in window), try global LHS
        if contextual_lhs == 2.0:  # DEFAULT_HEATING_SLOPE
            global_lhs = await self._model_storage.get_learned_heating_slope()
            if global_lhs != 2.0:  # If we have learned data, use it
                _LOGGER.warning(
                    "No slopes in time window (%.1f hours before %s), using global LHS: %.2f°C/h",
                    self._lhs_window_hours,
                    target_time.isoformat(),
                    global_lhs
                )
                return global_lhs
        
        return contextual_lhs
    
    async def calculate_and_schedule_anticipation(self) -> dict | None:
        """Calculate anticipation and schedule heating start.
        
        Returns:
            Dict with anticipation data for sensors, or None if not applicable
        """
        # Check if the currently tracked scheduler has been disabled
        if self._active_scheduler_entity:
            if not await self._scheduler_reader.is_scheduler_enabled(self._active_scheduler_entity):
                _LOGGER.warning(
                    "Active scheduler %s has been disabled. Clearing anticipation state.",
                    self._active_scheduler_entity
                )
                self._clear_anticipation_state()
                # Return None to clear sensor values
                return None
        
        # Get next timeslot
        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            _LOGGER.debug("No scheduled timeslot found")
            # Clear all tracking state when no timeslot is available
            # This handles both the case where the scheduler was just disabled
            # and when _active_scheduler_entity is already None
            if self._is_preheating_active or self._active_scheduler_entity or self._preheating_target_time:
                _LOGGER.info("Clearing anticipation state (no timeslot available)")
                self._clear_anticipation_state()
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
                "next_target_temperature": timeslot.target_temp,
                "anticipation_minutes": 0,
                "current_temp": environment.current_temp,
                "learned_heating_slope": lhs,
                "confidence_level": 100,
                "timeslot_id": timeslot.timeslot_id,
                "scheduler_entity": timeslot.scheduler_entity,
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
        
        # Track the active scheduler entity (for later disable detection)
        # This must be set BEFORE calling _schedule_anticipation so that
        # subsequent disable events can be properly detected
        if self._active_scheduler_entity != timeslot.scheduler_entity:
            _LOGGER.debug("Tracking scheduler entity: %s", timeslot.scheduler_entity)
            self._active_scheduler_entity = timeslot.scheduler_entity
        
        # Schedule if needed
        await self._schedule_anticipation(
            anticipated_start=prediction.anticipated_start_time,
            target_time=timeslot.target_time,
            target_temp=timeslot.target_temp,
            scheduler_entity_id=timeslot.scheduler_entity,
            lhs=prediction.learned_heating_slope,
        )
        
        # Return data for sensors
        return {
            "anticipated_start_time": prediction.anticipated_start_time,
            "next_schedule_time": timeslot.target_time,
            "next_target_temperature": timeslot.target_temp,
            "anticipation_minutes": prediction.estimated_duration_minutes,
            "current_temp": environment.current_temp,
            "learned_heating_slope": prediction.learned_heating_slope,
            "confidence_level": prediction.confidence_level,
            "timeslot_id": timeslot.timeslot_id,
            "scheduler_entity": timeslot.scheduler_entity,
        }
    
    async def _schedule_anticipation(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        lhs: float,
    ) -> None:
        """Schedule anticipated heating start and handle revert logic.
        
        This method handles both starting pre-heating and reverting to the current
        scheduled state when conditions change (e.g., anticipated start time moves later).
        
        Args:
            anticipated_start: When to start heating
            target_time: Target schedule time
            target_temp: Target temperature
            lhs: Learned heating slope used
        """
        now = dt_util.now()
        
        # Check if scheduler is enabled before proceeding
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning(
                "Scheduler %s is disabled. Skipping anticipation scheduling.",
                scheduler_entity_id
            )
            # If we were tracking this scheduler, clear the state
            if self._active_scheduler_entity == scheduler_entity_id:
                self._clear_anticipation_state()
            return
        
        # Check if we're currently pre-heating and should revert
        if self._is_preheating_active:
            # If anticipated start moved to the future (after now), we should stop pre-heating
            if anticipated_start > now and self._preheating_target_time == target_time:
                _LOGGER.warning(
                    "Anticipated start time moved later (now: %s, new start: %s). "
                    "LHS improved from %.2f to %.2f°C/h. Reverting to current scheduled state.",
                    now.isoformat(),
                    anticipated_start.isoformat(),
                    self._last_scheduled_lhs or 0.0,
                    lhs
                )
                # Check scheduler is still enabled before calling cancel_action
                if await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
                    await self._scheduler_commander.cancel_action(scheduler_entity_id)
                else:
                    _LOGGER.warning(
                        "Scheduler %s is now disabled. Cannot cancel action.",
                        scheduler_entity_id
                    )
                self._clear_anticipation_state()
                # Update tracking for new anticipated time
                self._last_scheduled_time = anticipated_start
                self._last_scheduled_lhs = lhs
                return
            
            # If we've reached the target time, mark pre-heating as complete
            if now >= target_time:
                _LOGGER.info("Target time reached, pre-heating complete")
                self._is_preheating_active = False
                self._preheating_target_time = None
                self._active_scheduler_entity = None
                return
        
        # Check for duplicate scheduling (only if not already pre-heating)
        if (
            not self._is_preheating_active
            and self._last_scheduled_time == anticipated_start
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
                "Anticipated start %s is past, triggering pre-heating immediately",
                anticipated_start.isoformat()
            )
            # Check scheduler is enabled before calling run_action
            if await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
                # Use ONLY the scheduler's run_action - it will handle VTherm state correctly
                # Respects scheduler conditions (skip_conditions=False in the adapter)
                await self._scheduler_commander.run_action(target_time, scheduler_entity_id)
                self._is_preheating_active = True
                self._preheating_target_time = target_time
                self._active_scheduler_entity = scheduler_entity_id
            else:
                _LOGGER.warning(
                    "Scheduler %s is disabled. Cannot trigger pre-heating.",
                    scheduler_entity_id
                )
            return
        
        # If both are in past, skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are past, skipping")
            return
        
        # Anticipated start is in the future - wait for it
        _LOGGER.info(
            "Anticipation scheduled: start at %s for target %s (waiting %.1f minutes)",
            anticipated_start.isoformat(),
            target_time.isoformat(),
            (anticipated_start - now).total_seconds() / 60.0
        )
        # Track which scheduler we're anticipating for
        self._active_scheduler_entity = scheduler_entity_id
        # Note: Actual scheduling is triggered by periodic updates from event_bridge
    
    async def check_overshoot_risk(self, scheduler_entity_id: str) -> None:
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
                "Overshoot risk! Current: %.1f°C, estimated: %.1f°C, target: %.1f°C - reverting to current schedule",
                environment.current_temp,
                estimated_temp,
                timeslot.target_temp
            )
            # Check scheduler is enabled before calling cancel_action
            if await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
                # Revert to current scheduled state instead of directly turning off
                # This respects scheduler conditions and returns to the proper setpoint
                await self._scheduler_commander.cancel_action(scheduler_entity_id)
            else:
                _LOGGER.warning(
                    "Scheduler %s is disabled. Cannot cancel action for overshoot prevention.",
                    scheduler_entity_id
                )
            self._clear_anticipation_state()
    
    async def reset_learned_slopes(self) -> None:
        """Reset all learned slope history."""
        _LOGGER.info("Resetting learned heating slope history")
        await self._model_storage.clear_slope_history()
