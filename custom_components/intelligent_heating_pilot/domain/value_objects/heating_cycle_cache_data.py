"""Value object for heating cycle cache data.

This value object represents cached heating cycle data with metadata
about when the cache was last updated. Designed to enable incremental
cycle extraction without re-scanning entire recorder history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .heating import HeatingCycle


@dataclass(frozen=True)
class HeatingCycleCacheData:
    """Immutable record of cached heating cycles with metadata.

    This value object stores a collection of heating cycles along with
    metadata about when the cache was last updated, enabling incremental
    cache refresh strategies, and tracks which dates have been explored
    even if they contained no cycles.

    Attributes:
        device_id: Device identifier these cycles belong to
        cycles: List of cached HeatingCycle objects
        last_search_time: UTC timestamp of the last history search
        retention_days: Number of days to retain cycles in cache
        explored_dates: Set of dates that have been extracted/explored
                       (even if no cycles were found). Used to avoid
                       re-extracting empty days indefinitely.
    """

    device_id: str
    cycles: tuple[HeatingCycle, ...]  # Use tuple for immutability
    last_search_time: datetime
    retention_days: int
    explored_dates: frozenset[date] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Validate cache data after initialization."""
        if not self.device_id:
            raise ValueError("device_id cannot be empty")

        if self.retention_days <= 0:
            raise ValueError(f"retention_days must be positive, got {self.retention_days}")

        # Ensure timestamp is timezone-aware
        if self.last_search_time.tzinfo is None:
            raise ValueError("last_search_time must be timezone-aware (UTC)")

    @property
    def cycle_count(self) -> int:
        """Return the number of cycles in the cache."""
        return len(self.cycles)

    def get_cycles_since(self, start_time: datetime) -> list[HeatingCycle]:
        """Get cycles that started on or after the specified time.

        Args:
            start_time: Minimum start time for cycles to return

        Returns:
            List of cycles starting at or after start_time
        """
        return [cycle for cycle in self.cycles if cycle.start_time >= start_time]

    def get_cycles_within_retention(self, reference_time: datetime) -> list[HeatingCycle]:
        """Get cycles within the retention period from a reference time.

        Args:
            reference_time: Time to calculate retention from

        Returns:
            List of cycles within retention period
        """
        from datetime import timedelta

        cutoff_time = reference_time - timedelta(days=self.retention_days)
        return [cycle for cycle in self.cycles if cycle.start_time >= cutoff_time]

    def with_explored_dates(self, explored_dates: set[date]) -> HeatingCycleCacheData:
        """Return a new cache instance with updated explored_dates.

        Since this dataclass is immutable (frozen=True), this method creates
        a new instance rather than modifying the existing one.

        Args:
            explored_dates: Set of dates to mark as explored

        Returns:
            A new HeatingCycleCacheData instance with updated explored_dates
        """
        return HeatingCycleCacheData(
            device_id=self.device_id,
            cycles=self.cycles,
            last_search_time=self.last_search_time,
            retention_days=self.retention_days,
            explored_dates=frozenset(explored_dates),
        )
