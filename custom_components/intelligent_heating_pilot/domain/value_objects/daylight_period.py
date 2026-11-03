"""Daylight period value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DaylightPeriod:
    """The time between one sunrise and the following sunset.

    The prediction scales the solar gain by the share of the heating phase spent in
    daylight: a clear sky does not warm a room before sunrise (#257).

    Attributes:
        sunrise: When the sun rises above the horizon (timezone-aware)
        sunset: When the sun sets below the horizon (timezone-aware)
    """

    sunrise: datetime
    sunset: datetime

    def __post_init__(self) -> None:
        """Reject a period that ends before it starts."""
        if self.sunset <= self.sunrise:
            raise ValueError(f"Sunset must come after sunrise, got {self.sunrise} -> {self.sunset}")

    def overlap_minutes(self, start: datetime, end: datetime) -> float:
        """Return how many minutes of ``[start, end]`` fall within this period.

        Args:
            start: Start of the window
            end: End of the window

        Returns:
            Overlap in minutes, 0.0 when the window is outside the period
        """
        overlap_start = max(start, self.sunrise)
        overlap_end = min(end, self.sunset)
        if overlap_end <= overlap_start:
            return 0.0
        return (overlap_end - overlap_start).total_seconds() / 60.0
