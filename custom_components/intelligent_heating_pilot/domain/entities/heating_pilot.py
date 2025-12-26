"""Heating pilot - the aggregate root for heating decisions."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..interfaces import ISchedulerCommander
from ..interfaces.decision_strategy import IDecisionStrategy
from ..value_objects import (
    EnvironmentState,
    HeatingDecision,
)

_LOGGER = logging.getLogger(__name__)


class HeatingPilot:
    """Coordinates heating decisions for a single VTherm.
    
    This is the aggregate root that orchestrates all domain logic
    for intelligent heating control. It delegates decision-making to
    a configurable strategy, allowing users to choose between:
    
    - Simple rule-based decisions (no ML required)
    - ML-powered decisions (requires IHP-ML-Models add-on)
    
    This design follows the Strategy pattern, making the pilot
    independent of the decision algorithm complexity.
    
    Attributes:
        _decision_strategy: Strategy for making heating decisions
        _scheduler_commander: Interface to control scheduler actions
    """
    
    def __init__(
        self,
        decision_strategy: IDecisionStrategy,
        scheduler_commander: ISchedulerCommander,
    ) -> None:
        """Initialize the heating pilot.
        
        Args:
            decision_strategy: Strategy for making heating decisions
                              (simple rules or ML-based)
            scheduler_commander: Implementation of scheduler control interface
        """
        _LOGGER.debug("Initializing HeatingPilot")
        self._decision_strategy = decision_strategy
        self._scheduler_commander = scheduler_commander
        _LOGGER.debug(f"HeatingPilot initialized with strategy: {type(decision_strategy).__name__}")
    
    async def decide_heating_action(
        self,
        environment: EnvironmentState,
    ) -> HeatingDecision:
        """Decide what heating action to take based on current conditions.
        
        This method delegates the decision to the configured strategy,
        which can be either simple rule-based or ML-powered.
        
        Args:
            environment: Current environmental conditions
            
        Returns:
            A heating decision with the action to take
        """
        _LOGGER.debug("HeatingPilot.decide_heating_action called")
        _LOGGER.debug(f"Delegating decision to {type(self._decision_strategy).__name__}")
        
        decision = await self._decision_strategy.decide_heating_action(environment)
        
        _LOGGER.info(f"HeatingPilot decision: {decision.action.value}")
        return decision
    
    async def check_overshoot_risk(
        self,
        environment: EnvironmentState,
        current_slope: float,
    ) -> HeatingDecision:
        """Check if heating should stop to prevent overshooting target.
        
        This method delegates the overshoot check to the configured strategy.
        
        Args:
            environment: Current environmental conditions
            current_slope: Current heating rate in °C/hour
            
        Returns:
            Decision to stop heating if overshoot is detected
        """
        _LOGGER.debug("HeatingPilot.check_overshoot_risk called")
        _LOGGER.debug(f"Delegating overshoot check to {type(self._decision_strategy).__name__}")
        
        decision = await self._decision_strategy.check_overshoot_risk(
            environment, 
            current_slope
        )
        
        _LOGGER.info(f"HeatingPilot overshoot check: {decision.action.value}")
        return decision
