"""Scheduler reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects import ScheduledTimeslot


class ISchedulerReader(ABC):
    """Contract for reading scheduled heating timeslots.

    Implementations of this interface retrieve schedule information
    from external scheduling systems (e.g., Home Assistant scheduler).

    See: https://github.com/nielsfaber/scheduler-component/#data-format
    """

    @abstractmethod
    async def get_next_timeslot(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> ScheduledTimeslot | None:
        """Retrieve the next scheduled heating timeslot.

        Scans all configured scheduler entities except those listed in
        ``exclude_entity_ids`` and returns the earliest upcoming timeslot
        among the remaining ones.

        Args:
            exclude_entity_ids: Scheduler entity ids to skip for this call —
                typically schedulers already confirmed blocked earlier in the
                same recalculation cycle. Empty by default, which reproduces
                today's behavior exactly.

        Returns:
            The next schedule timeslot among non-excluded schedulers, or
            None if none qualify or no scheduler entities are configured.
        """
        pass

    @abstractmethod
    async def is_scheduler_enabled(self, scheduler_entity_id: str) -> bool:
        """Check if a specific scheduler is enabled.

        Args:
            scheduler_entity_id: The scheduler entity ID to check

        Returns:
            True if the scheduler is enabled (state != "off"), False otherwise
        """
        pass
