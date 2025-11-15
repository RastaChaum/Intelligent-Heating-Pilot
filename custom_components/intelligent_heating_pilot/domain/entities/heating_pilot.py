"""Heating pilot - the aggregate root for heating decisions."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..interfaces import ISchedulerReader, IModelStorage, ISchedulerCommander
from ..value_objects import (
    EnvironmentState,
    HeatingDecision,
    HeatingAction,
    PredictionResult,
)
from ..services.prediction_service import PredictionService


class HeatingPilot:
    """Coordinates heating decisions for a single VTherm.
    
    This is the aggregate root that orchestrates all domain logic
    for intelligent heating control. It uses external services through
    interfaces without knowing their implementation details.
    
    Attributes:
        _scheduler_reader: Interface to read scheduled timeslots
        _storage: Interface to persist learned data
        _scheduler_commander: Interface to control scheduler actions
        _prediction_service: Service for prediction calculations
    """
    
    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        model_storage: IModelStorage,
        scheduler_commander: ISchedulerCommander,
    ) -> None:
        """Initialize the heating pilot.
        
        Args:
            scheduler_reader: Implementation of scheduler reading interface
            model_storage: Implementation of model storage interface
            scheduler_commander: Implementation of scheduler control interface
        """
        self._scheduler_reader = scheduler_reader
        self._storage = model_storage
        self._scheduler_commander = scheduler_commander
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
        # Get next scheduled timeslot
        next_timeslot = await self._scheduler_reader.get_next_timeslot()
        
        if next_timeslot is None:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled timeslots found"
            )
        
        # Check if target temperature is already reached
        current_temp = environment.current_temp
        if current_temp >= next_timeslot.target_temp:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason=f"Already at target temperature ({current_temp:.1f}°C >= {next_timeslot.target_temp:.1f}°C)"
            )
        
        # Get learned heating slope
        lhs = await self._storage.get_learned_heating_slope()
        
        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.current_temp,
            target_temp=next_timeslot.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.humidity,
            learned_slope=lhs,
            target_time=next_timeslot.target_time,
            cloud_coverage=environment.cloud_coverage,
        )
        
        # Decide based on anticipated start time
        now = environment.timestamp
        
        if prediction.anticipated_start_time <= now < next_timeslot.target_time:
            return HeatingDecision(
                action=HeatingAction.START_HEATING,
                target_temp=next_timeslot.target_temp,
                reason=f"Time to start heating (anticipated start: {prediction.anticipated_start_time.isoformat()})"
            )
        elif now >= next_timeslot.target_time:
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
        next_timeslot = await self._scheduler_reader.get_next_timeslot()
        
        if next_timeslot is None:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled timeslot to check against"
            )
        
        # Calculate estimated temperature at target time
        time_to_target = (next_timeslot.target_time - environment.timestamp).total_seconds() / 3600.0
        
        if time_to_target <= 0:
            return HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="Target time reached"
            )
        
        estimated_temp = environment.current_temp + (current_slope * time_to_target)
        
        # Stop if we'll overshoot by more than 0.5°C
        overshoot_threshold = next_timeslot.target_temp + 0.5
        
        if estimated_temp > overshoot_threshold:
            return HeatingDecision(
                action=HeatingAction.STOP_HEATING,
                reason=f"Overshoot risk detected (estimated: {estimated_temp:.1f}°C > threshold: {overshoot_threshold:.1f}°C)"
            )
        
        return HeatingDecision(
            action=HeatingAction.MONITOR,
            reason=f"No overshoot risk (estimated: {estimated_temp:.1f}°C)"
        )
