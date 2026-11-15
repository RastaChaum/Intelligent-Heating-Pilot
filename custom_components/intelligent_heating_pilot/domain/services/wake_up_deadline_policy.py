"""Wake-up deadline policy: when a source's point in time counts as a deadline."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..value_objects.wake_up_reading import WakeUpReading


class WakeUpDeadlinePolicy:
    """Judges whether a wake-up reading is a usable deadline.

    A value is ignored when it is absent, not in the future, or further away than the
    horizon: a stale value or a distant alarm must not start a preheat by accident.
    The policy holds no state.
    """

    def judge(self, reading: WakeUpReading, now: datetime, horizon: timedelta) -> datetime | None:
        """Return the deadline of a reading, or None when it is not usable.

        Args:
            reading: What the source held.
            now: Current time (timezone-aware).
            horizon: How far ahead a deadline may be.

        Returns:
            The deadline when it is after ``now`` and at most ``horizon`` ahead, else None.
        """
        value = reading.value
        if value is None or value <= now:
            return None
        if value - now > horizon:
            return None
        return value
