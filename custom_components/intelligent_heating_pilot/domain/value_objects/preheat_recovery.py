"""Preheat recovery value object: what reconciling a persisted preheat found."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .scheduled_timeslot import ScheduledTimeslot


class RecoveryOutcome(Enum):
    """The result of reconciling a preheat persisted before a restart or a reload."""

    NOTHING = "nothing"  # no preheat to resume (none recorded, or someone else took over)
    RESUMED = "resumed"  # the preheat for the next slot goes on
    RELEASED = "released"  # a stale preheat was undone or discarded
    DEFERRED = "deferred"  # the scheduler could not answer yet: the record is kept, ask again
    HOLDING = "holding"  # a wake-up deadline has passed and its hold is still running


@dataclass(frozen=True)
class PreheatRecovery:
    """The outcome of a recovery, with the slot when the preheat resumes.

    Attributes:
        outcome: What the reconciliation found.
        timeslot: The slot whose preheat resumes or whose hold runs; set for ``RESUMED`` and
            ``HOLDING``.
        hold_until: When the running hold ends; set only for ``HOLDING``.
    """

    outcome: RecoveryOutcome
    timeslot: ScheduledTimeslot | None = None
    hold_until: datetime | None = None

    def __post_init__(self) -> None:
        """Validate that a resumed recovery names its slot.

        Raises:
            ValueError: If the outcome is ``RESUMED`` without a slot.
        """
        if self.outcome is RecoveryOutcome.RESUMED and self.timeslot is None:
            raise ValueError("A resumed recovery needs its timeslot")
        if self.outcome is RecoveryOutcome.HOLDING and (
            self.timeslot is None or self.hold_until is None
        ):
            raise ValueError("A holding recovery needs its timeslot and the end of the hold")
