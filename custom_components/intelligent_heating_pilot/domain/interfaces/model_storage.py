"""Model storage interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects import SlopeData


class IModelStorage(ABC):
    """Contract for persisting machine learning model data.
    
    Implementations of this interface handle storage and retrieval
    of learned heating slopes and other model parameters.
    """
    
    @abstractmethod
    async def save_slope_in_history(self, slope: float) -> None:
        """Persist a newly learned heating slope in history.
        
        DEPRECATED: Use save_slope_data() instead. This method is kept
        for backward compatibility and creates a SlopeData internally.
        
        Args:
            slope: Heating slope value in °C/hour
        """
        pass
    
    @abstractmethod
    async def save_slope_data(self, slope_data: SlopeData) -> None:
        """Persist a timestamped slope measurement.
        
        Args:
            slope_data: Slope data with timestamp and value
        """
        pass
    
    @abstractmethod
    async def get_slopes_in_history(self) -> list[float]:
        """Retrieve historical learned heating slopes (values only).
        
        DEPRECATED: Use get_all_slope_data() for timestamped data.
        This method is kept for backward compatibility.
        
        Returns:
            List of learned slope values in °C/hour, ordered from oldest to newest.
        """
        pass
    
    @abstractmethod
    async def get_all_slope_data(self) -> list[SlopeData]:
        """Retrieve all historical slope data with timestamps.
        
        Returns:
            List of SlopeData objects, ordered from oldest to newest.
        """
        pass
    
    @abstractmethod
    async def get_slopes_in_time_window(
        self,
        before_time: datetime,
        window_hours: float
    ) -> list[SlopeData]:
        """Retrieve slopes within a time window before a given time.
        
        Args:
            before_time: End of the time window (exclusive)
            window_hours: Size of the time window in hours
            
        Returns:
            List of SlopeData within the window, ordered from oldest to newest.
            Empty list if no data available in the window.
        """
        pass
    
    @abstractmethod
    async def get_learned_heating_slope(self) -> float:
        """Get the current learned heating slope (LHS).
        
        This represents the system's best estimate of the heating rate
        based on all historical data.
        
        Returns:
            The learned heating slope in °C/hour.
        """
        pass
    
    @abstractmethod
    async def clear_slope_history(self) -> None:
        """Clear all learned slope data from history.
        
        This resets the learning system to its initial state.
        """
        pass
