"""Preheat record value object: the climate's state before IHP acted for one slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .climate_snapshot import ClimateSnapshot
from .slot_action import SlotAction


@dataclass(frozen=True)
class PreheatRecord:
    """What IHP needs to undo a preheat without overriding anybody.

    One record exists per IHP instance. It is saved once per slot, before the first command,
    and kept across a restart so that a stale preheat can still be reconciled.

    Attributes:
        timeslot_id: Identity of the slot the preheat was started for.
        scheduler_entity: Entity id of the scheduler that owns the slot.
        slot_time: When the slot starts (timezone-aware).
        previous: Climate state before IHP acted.
        applied: The action IHP applied.
        recorded_at: When the record was made (timezone-aware).
    """

    timeslot_id: str
    scheduler_entity: str
    slot_time: datetime
    previous: ClimateSnapshot
    applied: SlotAction
    recorded_at: datetime

    def __post_init__(self) -> None:
        """Validate the record.

        Raises:
            ValueError: If an identifier is blank or a datetime has no timezone.
        """
        if not self.timeslot_id:
            raise ValueError("A preheat record needs a timeslot_id")
        if not self.scheduler_entity:
            raise ValueError("A preheat record needs a scheduler_entity")
        if self.slot_time.tzinfo is None or self.recorded_at.tzinfo is None:
            raise ValueError("Preheat record datetimes must carry a timezone")
