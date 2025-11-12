"""Scheduler reader interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects import ScheduleEvent


class ISchedulerReader(ABC):
    """Contract for reading scheduled heating events.
    
    Implementations of this interface retrieve schedule information
    from external scheduling systems (e.g., Home Assistant scheduler).
    """
    
    @abstractmethod
    async def get_next_event(self) -> ScheduleEvent | None:
        """Retrieve the next scheduled heating event.
        
        Returns:
            The next schedule event, or None if no events are scheduled.
        """
        pass
