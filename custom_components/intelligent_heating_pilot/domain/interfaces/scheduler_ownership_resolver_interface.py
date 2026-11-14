"""Scheduler ownership resolver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.scheduler_kind import SchedulerKind


class ISchedulerOwnershipResolver(ABC):
    """Contract for telling which scheduler integration owns an entity.

    Schedulers can look alike (Climate Scheduler imitates the HACS Scheduler attributes), so
    ownership comes from where the entity is registered, not from how it looks.
    """

    @abstractmethod
    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        """Return the kind of scheduler that owns the entity.

        Args:
            scheduler_entity_id: Entity id of the scheduler.

        Returns:
            ``UNKNOWN`` when the owner cannot be established.
        """
