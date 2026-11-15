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
        claimed: True once somebody else changed the climate after IHP acted. A claimed record
            is kept until its slot, so that IHP does not apply the slot again over that change.
        hold_until: For a wake-up slot with a hold, when the hold ends and the earlier state is
            put back; None when there is no hold.
        hold_handoff: True when a scheduler slot bounds the hold: the scheduler then owns the
            setting and nothing is restored.
    """

    timeslot_id: str
    scheduler_entity: str
    slot_time: datetime
    previous: ClimateSnapshot
    applied: SlotAction
    recorded_at: datetime
    claimed: bool = False
    hold_until: datetime | None = None
    hold_handoff: bool = False

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
        if self.hold_until is not None and self.hold_until.tzinfo is None:
            raise ValueError("Preheat record datetimes must carry a timezone")
