"""Model storage interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IModelStorage(ABC):
    """Contract for persisting machine learning model data.
    
    Implementations of this interface handle storage and retrieval
    of learned heating slopes and other model parameters.
    """
    
    @abstractmethod
    async def save_learned_slope(self, slope: float) -> None:
        """Persist a newly learned heating slope.
        
        Args:
            slope: Heating slope value in °C/hour
        """
        pass
    
    @abstractmethod
    async def get_learned_slopes(self) -> list[float]:
        """Retrieve historical learned heating slopes.
        
        Returns:
            List of learned slope values in °C/hour, ordered from oldest to newest.
        """
        pass
    
    @abstractmethod
    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).
        
        This represents the system's best estimate of the heating rate
        based on historical data.
        
        Returns:
            The learned heating slope in °C/hour.
        """
        pass
    
    @abstractmethod
    async def clear_learning_history(self) -> None:
        """Clear all learned slope data.
        
        This resets the learning system to its initial state.
        """
        pass
