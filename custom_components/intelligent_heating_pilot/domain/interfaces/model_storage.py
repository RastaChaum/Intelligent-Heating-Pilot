"""Model storage interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IModelStorage(ABC):
    """Contract for persisting machine learning model data.
    
    Implementations of this interface handle storage and retrieval
    of learned heating slopes and other model parameters.
    
    NOTE: Direct slope data persistence (save_slope_*) has been removed.
    Slopes are now extracted directly from Home Assistant recorder via
    HeatingCycleService. This interface now only provides access to the
    global learned heating slope (LHS) and cleanup operations.
    """
    
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

    @abstractmethod
    async def get_cached_global_lhs(self) -> LHSCacheEntry | None:
        """Return cached global LHS if available."""

    @abstractmethod
    async def set_cached_global_lhs(self, lhs: float, updated_at: datetime) -> None:
        """Persist global LHS cache with timestamp."""

    @abstractmethod
    async def get_cached_contextual_lhs(self, hour: int) -> LHSCacheEntry | None:
        """Return cached contextual LHS for the given hour if available."""

    @abstractmethod
    async def set_cached_contextual_lhs(self, hour: int, lhs: float, updated_at: datetime) -> None:
        """Persist contextual LHS cache for the given hour with timestamp."""
