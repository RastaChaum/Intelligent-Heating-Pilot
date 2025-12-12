"""Simple rule-based decision strategy."""
from __future__ import annotations

import logging

from ..interfaces import ISchedulerReader, IModelStorage
from ..interfaces.decision_strategy import IDecisionStrategy
from ..value_objects import (
    EnvironmentState,
    HeatingDecision,
    HeatingAction,
)
from ..services.prediction_service import PredictionService

_LOGGER = logging.getLogger(__name__)


class SimpleDecisionStrategy(IDecisionStrategy):
    """Rule-based heating decisions without ML.
    
    This strategy uses simple predictive calculations based on
    learned heating slopes. It's easier to set up as it doesn't
    require the IHP-ML-Models add-on.
    
    Decision logic:
    - Uses learned heating slope (LHS) from past heating cycles
    - Calculates anticipated start time based on current conditions
    - Prevents overshooting with conservative thresholds
    
    Attributes:
        _scheduler_reader: Interface to read scheduled timeslots
        _storage: Interface to access learned data
        _prediction_service: Service for prediction calculations
    """
    
    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        model_storage: IModelStorage,
    ) -> None:
        """Initialize simple decision strategy.
        
        Args:
            scheduler_reader: Implementation of scheduler reading interface
            model_storage: Implementation of model storage interface
        """
        _LOGGER.info("Initializing SimpleDecisionStrategy")
        self._scheduler_reader = scheduler_reader
        self._storage = model_storage
        self._prediction_service = PredictionService()
        _LOGGER.debug("SimpleDecisionStrategy initialized with scheduler and storage")
    
    async def decide_heating_action(
        self,
        environment: EnvironmentState,
    ) -> HeatingDecision:
        """Decide heating action using simple rules.
        
        Args:
            environment: Current environmental conditions
            
        Returns:
            A heating decision based on simple predictive rules
        """
        _LOGGER.info("SimpleDecisionStrategy.decide_heating_action called")
        _LOGGER.debug(f"Environment: indoor={environment.indoor_temperature}°C, "
                     f"outdoor={environment.outdoor_temp}°C, "
                     f"humidity={environment.indoor_humidity}%")
        
        # Get next scheduled timeslot
        next_timeslot = await self._scheduler_reader.get_next_timeslot()
        
        if next_timeslot is None:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled timeslots found"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        
        # Check if target temperature is already reached
        current_temp = environment.indoor_temperature
        if current_temp >= next_timeslot.target_temp:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason=f"Already at target temperature ({current_temp:.1f}°C >= {next_timeslot.target_temp:.1f}°C)"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        
        # Get learned heating slope
        lhs = await self._storage.get_learned_heating_slope()
        _LOGGER.debug(f"Learned heating slope: {lhs:.4f}°C/hour")
        
        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.indoor_temperature,
            target_temp=next_timeslot.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.indoor_humidity,
            learned_slope=lhs,
            target_time=next_timeslot.target_time,
            cloud_coverage=environment.cloud_coverage,
        )
        
        _LOGGER.debug(f"Prediction: anticipated_start={prediction.anticipated_start_time.isoformat()}, "
                     f"duration={prediction.estimated_duration_minutes:.1f}min, "
                     f"confidence={prediction.confidence_level:.2f}")
        
        # Decide based on anticipated start time
        now = environment.timestamp
        
        if prediction.anticipated_start_time <= now < next_timeslot.target_time:
            decision = HeatingDecision(
                action=HeatingAction.START_HEATING,
                target_temp=next_timeslot.target_temp,
                reason=f"Time to start heating (anticipated start: {prediction.anticipated_start_time.isoformat()})"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        elif now >= next_timeslot.target_time:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="Schedule time has passed"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        else:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason=f"Wait until {prediction.anticipated_start_time.isoformat()}"
            )
            _LOGGER.debug(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
    
    async def check_overshoot_risk(
        self,
        environment: EnvironmentState,
        current_slope: float,
    ) -> HeatingDecision:
        """Check overshoot risk using simple calculations.
        
        Args:
            environment: Current environmental conditions
            current_slope: Current heating rate in °C/hour
            
        Returns:
            Decision to stop heating if overshoot is detected
        """
        _LOGGER.info("SimpleDecisionStrategy.check_overshoot_risk called")
        _LOGGER.debug(f"Current slope: {current_slope:.4f}°C/hour, "
                     f"indoor_temp={environment.indoor_temperature}°C")
        
        next_timeslot = await self._scheduler_reader.get_next_timeslot()
        
        if next_timeslot is None:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="No scheduled timeslot to check against"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        
        # Calculate estimated temperature at target time
        time_to_target = (next_timeslot.target_time - environment.timestamp).total_seconds() / 3600.0
        
        if time_to_target <= 0:
            decision = HeatingDecision(
                action=HeatingAction.NO_ACTION,
                reason="Target time reached"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        
        estimated_temp = environment.indoor_temperature + (current_slope * time_to_target)
        
        # Stop if we'll overshoot by more than 0.5°C
        overshoot_threshold = next_timeslot.target_temp + 0.5
        
        _LOGGER.debug(f"Estimated temp at target time: {estimated_temp:.1f}°C, "
                     f"threshold: {overshoot_threshold:.1f}°C")
        
        if estimated_temp > overshoot_threshold:
            decision = HeatingDecision(
                action=HeatingAction.STOP_HEATING,
                reason=f"Overshoot risk detected (estimated: {estimated_temp:.1f}°C > threshold: {overshoot_threshold:.1f}°C)"
            )
            _LOGGER.info(f"Decision: {decision.action.value} - {decision.reason}")
            return decision
        
        decision = HeatingDecision(
            action=HeatingAction.NO_ACTION,
            reason=f"No overshoot risk (estimated: {estimated_temp:.1f}°C)"
        )
        _LOGGER.debug(f"Decision: {decision.action.value} - {decision.reason}")
        return decision
