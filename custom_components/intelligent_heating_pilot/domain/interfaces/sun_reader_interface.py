"""Sun reader interface.

Contract for reading when the sun is above the horizon at the home's location.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects import DaylightPeriod


class ISunReader(ABC):
    """Contract for reading the daylight periods around a time window.

    The prediction applies the solar gain only to the part of the heating phase
    spent in daylight (#257). Implementations translate sunrise and sunset times
    of the home's location; they hold no business rule.
    """

    @abstractmethod
    async def get_daylight_periods(self, start: datetime, end: datetime) -> list[DaylightPeriod]:
        """Return the daylight periods of every local date between ``start`` and ``end``.

        Args:
            start: Start of the window (timezone-aware)
            end: End of the window (timezone-aware)

        Returns:
            One period per local date touched by the window, in chronological order.
            A date with no sunrise or no sunset (polar night or day) has no period.
            An empty list when the sun position is unknown.
        """
