"""Schedule timeslot value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScheduledTimeslot:
    """Represents a scheduled heating timeslot.
    
    A schedule timeslot defines when the room should reach a specific
    target temperature, following the scheduler component data format.
    See: https://github.com/nielsfaber/scheduler-component/#data-format
    
    Attributes:
        target_time: When the target temperature should be reached
        target_temp: Desired temperature in Celsius
        timeslot_id: Unique identifier for this schedule timeslot
        scheduler_entity: The scheduler entity ID that provided this timeslot
    """
    
    target_time: datetime
    target_temp: float
    timeslot_id: str
    scheduler_entity: str = ""
    
    def __post_init__(self) -> None:
        """Validate the schedule timeslot data."""
        if not self.timeslot_id:
            raise ValueError("Timeslot ID cannot be empty")
