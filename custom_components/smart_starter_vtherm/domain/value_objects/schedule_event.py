"""Schedule event value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScheduleEvent:
    """Represents a scheduled heating event.
    
    A schedule event defines when the room should reach a specific
    target temperature.
    
    Attributes:
        target_time: When the target temperature should be reached
        target_temp: Desired temperature in Celsius
        event_id: Unique identifier for this schedule event
    """
    
    target_time: datetime
    target_temp: float
    event_id: str
    
    def __post_init__(self) -> None:
        """Validate the schedule event data."""
        if not self.event_id:
            raise ValueError("Event ID cannot be empty")
