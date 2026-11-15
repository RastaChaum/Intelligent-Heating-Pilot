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

    async def get_next_scheduler_timeslot(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> ScheduledTimeslot | None:
        """Retrieve the next timeslot of the schedulers alone, wake-up sources left out.

        Used to know whether a scheduler will take over the setting before a hold ends. A
        reader that only knows schedulers answers like ``get_next_timeslot``.

        Args:
            exclude_entity_ids: Scheduler entity ids to skip for this call.

        Returns:
            The next scheduler timeslot, or None when there is none.
        """
        return await self.get_next_timeslot(exclude_entity_ids)

    @abstractmethod
    async def is_scheduler_enabled(self, scheduler_entity_id: str) -> bool:
        """Check if a specific scheduler is enabled.

        Args:
            scheduler_entity_id: The scheduler entity ID to check

        Returns:
            True if the scheduler is enabled (state != "off"), False otherwise
        """
        pass

    @abstractmethod
    async def get_next_timeslot_of(self, scheduler_entity_id: str) -> ScheduledTimeslot | None:
        """Retrieve the next timeslot of one scheduler.

        Unlike ``get_next_timeslot``, this ignores the other schedulers: it tells whether a
        given slot is still the next one *of its own scheduler*.

        Args:
            scheduler_entity_id: The scheduler entity ID to read.

        Returns:
            Its next timeslot, or None if it has none or is disabled.
        """
        pass
