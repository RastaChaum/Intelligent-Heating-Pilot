"""Slots around a moment value object."""

from __future__ import annotations

from dataclasses import dataclass

from .scheduled_timeslot import ScheduledTimeslot


@dataclass(frozen=True)
class SlotsAround:
    """The schedule slots around one moment.

    Absent means "the schedulers cannot say", never "there is none": a scheduler that exposes
    only its next slot cannot tell which slot is in effect.

    Attributes:
        in_effect: The slot in effect at the moment, when it can be told.
        following: The first slot starting after the moment, when it can be told.
    """

    in_effect: ScheduledTimeslot | None = None
    following: ScheduledTimeslot | None = None
