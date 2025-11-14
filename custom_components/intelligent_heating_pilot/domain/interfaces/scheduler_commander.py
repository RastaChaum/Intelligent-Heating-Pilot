"""Scheduler commander interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ISchedulerCommander(ABC):
    """Contract for scheduler control actions.
    
    Implementations of this interface execute scheduler commands using
    the scheduler component's run_action service.
    
    See: https://github.com/nielsfaber/scheduler-component/#schedulerrun_action
    """
    
    @abstractmethod
    async def run_action(self, target_time: datetime) -> None:
        """Trigger a scheduler action for a specific timeslot.
        
        This will start heating in the mode configured in the scheduler
        for the timeslot at the given time.
        
        Args:
            target_time: The time of the scheduler timeslot to trigger
        """
        pass
    
    @abstractmethod
    async def cancel_action(self) -> None:
        """Cancel current scheduler action and return to current timeslot.
        
        This is used to stop overshoot by reverting to the mode configured
        for the current time (now()).
        """
        pass
