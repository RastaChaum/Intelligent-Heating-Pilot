"""Shared rule giving the contextual hour of a moment.

The contextual LHS is written under the hour a heating cycle ends and read under
the hour of a scheduled slot. Both sides use this rule, so a slot reads the
cycles that preheated for it (#183, #214).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..value_objects.contextual_lhs_by_hour import HOURS_PER_DAY

HALF_HOUR = timedelta(minutes=30)


def contextual_hour(moment: datetime) -> int:
    """Return the hour of day nearest to a moment, read on its own clock.

    A preheat aims at its slot, but its cycle ends as soon as the room is within
    the detection threshold of the target, so it usually ends a little before
    the slot: 06:58 for a 07:00 slot. Taking the hour as is would file it under
    06:00, which the 07:00 slot never reads. The nearest hour keeps the cycles
    ending up to half an hour on either side of a whole-hour slot with it.

    A moment exactly on the half hour belongs to the earlier hour: cycles end
    before their slot rather than after it, so a 06:30 slot must read the hour
    holding the cycles that ended in the half hour before it.

    Only the wall clock is read, so the rule does not depend on the timezone
    offset or on the length of the day at a daylight saving time change.

    Args:
        moment: Naive or aware datetime, already on the clock of the slots.

    Returns:
        Hour of day (0-23). A moment after 23:30 maps to 0.
    """
    past_the_hour = timedelta(
        minutes=moment.minute, seconds=moment.second, microseconds=moment.microsecond
    )
    if past_the_hour > HALF_HOUR:
        return (moment.hour + 1) % HOURS_PER_DAY
    return moment.hour
