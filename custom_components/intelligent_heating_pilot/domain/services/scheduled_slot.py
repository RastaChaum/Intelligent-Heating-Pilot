"""Shared rule telling which scheduled slot a heating cycle was heating for.

A preheat that reaches the target long after its slot ends in a later hour than the
slot, so filing it by its end hides it from the slot that produced it (#254). The
cycle history holds no link to the slot, but the slots that came due are known: a
slot of the cycle's target that came due while the room was still heating toward
it is the slot the cycle was late for.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from ..constants import TEMP_FLOAT_TOLERANCE_C
from ..value_objects.historical_data import HistoricalMeasurement


def scheduled_slot_of_cycle(
    slots: Iterable[HistoricalMeasurement],
    start_time: datetime,
    end_time: datetime,
    target_temp: float,
) -> datetime | None:
    """Return the slot a cycle was heating for, if it came due during the cycle.

    A slot due exactly at the cycle start is not taken: the cycle started when the
    slot was applied, it did not preheat for it. A slot of another target (an eco
    slot coming due during a comfort preheat) is not the slot the cycle heated for.
    Cycles that end before their slot are not tied: the next slot after a cycle may
    as well be unrelated to it, such as an evening slot after an afternoon heat-up.

    Args:
        slots: Slots that came due, each timestamped when it came due and valued
            with its target temperature. Non-numeric values are ignored.
        start_time: Cycle start. Naive times are read as UTC.
        end_time: Cycle end. Naive times are read as UTC.
        target_temp: Target the cycle heated toward.

    Returns:
        The due time of the first matching slot, as recorded, or None.
    """
    start, end = _as_utc(start_time), _as_utc(end_time)
    matching = [
        slot.timestamp
        for slot in slots
        if start < _as_utc(slot.timestamp) <= end and _has_target(slot, target_temp)
    ]
    return min(matching, key=_as_utc, default=None)


def _has_target(slot: HistoricalMeasurement, target_temp: float) -> bool:
    """Whether a slot's recorded target is the cycle target."""
    value = slot.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return abs(float(value) - target_temp) <= TEMP_FLOAT_TOLERANCE_C


def _as_utc(moment: datetime) -> datetime:
    """Compare naive UTC and aware times as instants."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
