"""Decision strategy interface for heating control."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects import EnvironmentState, HeatingDecision


class IDecisionStrategy(ABC):
    """Contract for heating decision strategies.
    
    This interface allows different decision-making approaches:
    - Simple rule-based decisions (no ML required)
    - ML-based decisions (requires IHP-ML-Models)
    - Hybrid approaches combining both
    
    By abstracting the decision logic, we make the HeatingPilot
    agnostic to the complexity of the underlying decision process.
    """
    
    @abstractmethod
    async def decide_heating_action(
        self,
        environment: EnvironmentState,
    ) -> HeatingDecision:
        """Decide what heating action to take.
        
        Args:
            environment: Current environmental conditions
            
        Returns:
            A heating decision with the action to take
        """
        pass
    
    @abstractmethod
    async def check_overshoot_risk(
        self,
        environment: EnvironmentState,
        current_slope: float,
    ) -> HeatingDecision:
        """Check if heating should stop to prevent overshooting.
        
        Args:
            environment: Current environmental conditions
            current_slope: Current heating rate in °C/hour
            
        Returns:
            Decision to stop heating if overshoot is detected
        """
        pass
