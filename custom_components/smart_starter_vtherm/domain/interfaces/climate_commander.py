"""Climate commander interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IClimateCommander(ABC):
    """Contract for climate control actions.
    
    Implementations of this interface execute heating commands
    on the physical climate control system.
    """
    
    @abstractmethod
    async def start_heating(self, target_temp: float) -> None:
        """Begin heating to reach the specified target temperature.
        
        Args:
            target_temp: Desired temperature in Celsius
        """
        pass
    
    @abstractmethod
    async def stop_heating(self) -> None:
        """Stop the heating system."""
        pass
    
    @abstractmethod
    async def get_current_temperature(self) -> float:
        """Get the current room temperature.
        
        Returns:
            Current temperature in Celsius
        """
        pass
    
    @abstractmethod
    async def get_target_temperature(self) -> float | None:
        """Get the current target temperature setting.
        
        Returns:
            Target temperature in Celsius, or None if not set
        """
        pass
