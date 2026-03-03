"""LHS (Learned Heating Slope) storage interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from ..value_objects.lhs_cache_entry import LHSCacheEntry

if TYPE_CHECKING:
    pass


class ILhsStorage(ABC):
    """Contract for persisting learned heating slope (LHS) data.

    Implementations of this interface handle storage and retrieval
    of learned heating slopes (both global and contextual).

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
        """Return cached global LHS if available.

        Returns:
            LHSCacheEntry with global LHS value and timestamp, or None if not cached.
        """
        pass

    @abstractmethod
    async def set_cached_global_lhs(self, lhs: float, updated_at: datetime) -> None:
        """Persist global LHS cache with timestamp.

        Args:
            lhs: The learned heating slope value in °C/hour.
            updated_at: Timestamp when the LHS was calculated.
        """
        pass

    @abstractmethod
    async def get_cached_contextual_lhs(self, hour: int) -> LHSCacheEntry | None:
        """Return cached contextual LHS for the given hour if available.

        Args:
            hour: Hour of day (0-23) for which to retrieve contextual LHS.

        Returns:
            LHSCacheEntry with contextual LHS value and timestamp, or None if not cached.
        """
        pass

    @abstractmethod
    async def set_cached_contextual_lhs(self, hour: int, lhs: float, updated_at: datetime) -> None:
        """Persist contextual LHS cache for the given hour with timestamp.

        Args:
            hour: Hour of day (0-23) for which to cache the LHS.
            lhs: The learned heating slope value in °C/hour for this hour.
            updated_at: Timestamp when the LHS was calculated.
        """
        pass

    @abstractmethod
    async def clear_contextual_cache(self) -> None:
        """Clear all cached contextual LHS entries."""
        pass

    @abstractmethod
    async def get_learned_dead_time(self) -> float | None:
        """Get the current learned dead time in minutes.

        Dead time is the delay between starting heat output and when the
        indoor temperature begins rising noticeably.

        Returns:
            The learned dead time in minutes, or None if not yet learned.
        """
        pass

    @abstractmethod
    async def set_learned_dead_time(self, dead_time: float | None) -> None:
        """Persist the learned dead time value.

        Args:
            dead_time: The learned dead time in minutes, or None to clear.
        """
        pass
