"""Schedule timeslot value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .slot_action import SlotAction


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
        action: What the slot applies, when the scheduler gives a usable action. None for a
            slot without one (HACS delegation, unsupported scheduler, "no change" node).
        hold: For a wake-up source slot, how long after the deadline IHP puts the thermostat
            back in its earlier state. None for every other slot.
    """

    target_time: datetime
    target_temp: float
    timeslot_id: str
    scheduler_entity: str = ""
    action: SlotAction | None = None
    hold: timedelta | None = None

    def __post_init__(self) -> None:
        """Validate the schedule timeslot data."""
        if not self.timeslot_id:
            raise ValueError("Timeslot ID cannot be empty")
