"""Interface for heating cycle storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from ..value_objects.heating import HeatingCycle
from ..value_objects.heating_cycle_cache_data import HeatingCycleCacheData


class IHeatingCycleStorage(ABC):
    """Contract for persisting and retrieving heating cycle data.

    Implementations of this interface handle storage and retrieval of
    heating cycles with incremental update support to avoid repeatedly
    scanning the entire Home Assistant recorder history.
    """

    @abstractmethod
    async def get_cache_data(self, device_id: str) -> HeatingCycleCacheData | None:
        """Get cached cycle data for a device.

        Returns the complete cache data including cycles and metadata.
        Returns None if no cache exists for the device.

        Args:
            device_id: The device identifier

        Returns:
            HeatingCycleCacheData if cache exists, None otherwise
        """
        pass

    @abstractmethod
    async def append_cycles(
        self,
        device_id: str,
        new_cycles: list[HeatingCycle],
        search_end_time: datetime,
        retention_days: int | None = None,
    ) -> None:
        """Append new cycles to the cache and update search timestamp.

        This method adds new cycles to the existing cache (if any) and updates
        the last_search_time to track where the next incremental search should begin.
        Automatically handles deduplication based on cycle start_time.

        Args:
            device_id: The device identifier
            new_cycles: List of new cycles to append
            search_end_time: Timestamp marking the end of this search period
            retention_days: Optional retention days to store with cache metadata
        """
        pass

    @abstractmethod
    async def prune_old_cycles(
        self,
        device_id: str,
        reference_time: datetime,
    ) -> None:
        """Remove cycles older than the retention period.

        Args:
            device_id: The device identifier
            reference_time: Time to calculate retention from
        """
        pass

    @abstractmethod
    async def clear_cache(self, device_id: str) -> None:
        """Clear all cached cycles for a device.

        This resets the learning system to its initial state for the device.

        Args:
            device_id: The device identifier
        """
        pass

    @abstractmethod
    async def get_last_search_time(self, device_id: str) -> datetime | None:
        """Get the timestamp of the last cycle search.

        This is used to determine the start time for the next incremental search.
        Returns None if no previous search has been performed.

        Args:
            device_id: The device identifier

        Returns:
            UTC timestamp of last search, or None if no cache exists
        """
        pass

    @abstractmethod
    async def append_explored_dates(
        self,
        device_id: str,
        explored_dates: set[date],
    ) -> None:
        """Mark dates as explored (whether they contained cycles or not).

        This prevents re-extracting days that have already been examined,
        making explored_dates the single source of truth for coverage.

        Args:
            device_id: The device identifier
            explored_dates: Set of dates to mark as explored
        """
        pass
