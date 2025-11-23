"""Scheduler reader interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects import ScheduleTimeslot


class ISchedulerReader(ABC):
    """Contract for reading scheduled heating timeslots.
    
    Implementations of this interface retrieve schedule information
    from external scheduling systems (e.g., Home Assistant scheduler).
    
    See: https://github.com/nielsfaber/scheduler-component/#data-format
    """
    
    @abstractmethod
    async def get_next_timeslot(self) -> ScheduleTimeslot | None:
        """Retrieve the next scheduled heating timeslot.
        
        Returns:
            The next schedule timeslot, or None if no timeslots are scheduled.
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