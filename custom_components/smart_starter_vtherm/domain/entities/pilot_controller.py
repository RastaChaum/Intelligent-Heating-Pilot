"""Pilot controller - the aggregate root for heating decisions."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..interfaces import ISchedulerReader, IModelStorage, IClimateCommander
from ..value_objects import (
    EnvironmentState,
    HeatingDecision,
    HeatingAction,
    PredictionResult,
)
from ..services.prediction_service import PredictionService


class PilotController:
    """Coordinates heating decisions for a single VTherm.
    
    This is the aggregate root that orchestrates all domain logic
    for intelligent heating control. It uses external services through
    interfaces without knowing their implementation details.
    
    Attributes:
        _scheduler: Interface to read scheduled events
        _storage: Interface to persist learned data
        _commander: Interface to control climate system
        _prediction_service: Service for prediction calculations
    """
    
    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        model_storage: IModelStorage,
        climate_commander: IClimateCommander,
    ) -> None:
        """Initialize the pilot controller.
        
        Args:
            scheduler_reader: Implementation of scheduler reading interface
            model_storage: Implementation of model storage interface
            climate_commander: Implementation of climate control interface
        """
        self._scheduler = scheduler_reader
        self._storage = model_storage
        self._commander = climate_commander
        self._prediction_service = PredictionService()
    
    async def decide_heating_action(
        self,
        environment: EnvironmentState,
    ) -> HeatingDecision:
        """Decide what heating action to take based on current conditions.
        
        This is the main decision-making method that coordinates all
        domain logic to determine the appropriate heating action.
        
        Args:
            environment: Current environmental conditions
            
        Returns:
            A heating decision with the action to take
        """
        # Get next scheduled event
        next_event = await self._scheduler.get_next_event()
        
        if next_event is None:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled events found"
            )
        
        # Check if target temperature is already reached
        current_temp = environment.current_temp
        if current_temp >= next_event.target_temp:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason=f"Already at target temperature ({current_temp:.1f}°C >= {next_event.target_temp:.1f}°C)"
            )
        
        # Get learned heating slope
        lhs = await self._storage.get_learned_heating_slope()
        
        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.current_temp,
            target_temp=next_event.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.humidity,
            learned_slope=lhs,
            cloud_coverage=environment.cloud_coverage,
        )
        
        # Decide based on anticipated start time
        now = environment.timestamp
        
        if prediction.anticipated_start_time <= now < next_event.target_time:
            return HeatingDecision(
                action=HeatingAction.START_HEATING,
                target_temp=next_event.target_temp,
                reason=f"Time to start heating (anticipated start: {prediction.anticipated_start_time.isoformat()})"
            )
        elif now >= next_event.target_time:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="Schedule time has passed"
            )
        else:
            return HeatingDecision(
                action=HeatingAction.MONITOR,
                reason=f"Wait until {prediction.anticipated_start_time.isoformat()}"
            )
    
    async def check_overshoot_risk(
        self,
        environment: EnvironmentState,
        current_slope: float,
    ) -> HeatingDecision:
        """Check if heating should stop to prevent overshooting target.
        
        Args:
            environment: Current environmental conditions
            current_slope: Current heating rate in °C/hour
            
        Returns:
            Decision to stop heating if overshoot is detected
        """
        next_event = await self._scheduler.get_next_event()
        
        if next_event is None:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled event to check against"
            )
        
        # Calculate estimated temperature at target time
        time_to_target = (next_event.target_time - environment.timestamp).total_seconds() / 3600.0
        
        if time_to_target <= 0:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="Target time reached"
            )
        
        estimated_temp = environment.current_temp + (current_slope * time_to_target)
        
        # Stop if we'll overshoot by more than 0.5°C
        overshoot_threshold = next_event.target_temp + 0.5
        
        if estimated_temp > overshoot_threshold:
            return HeatingDecision(
                action=HeatingAction.STOP_HEATING,
                reason=f"Overshoot risk detected (estimated: {estimated_temp:.1f}°C > threshold: {overshoot_threshold:.1f}°C)"
            )
        
        return HeatingDecision(
            action=HeatingAction.MONITOR,
            reason=f"No overshoot risk (estimated: {estimated_temp:.1f}°C)"
        )
