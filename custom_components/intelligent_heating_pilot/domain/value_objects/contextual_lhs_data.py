"""Value object for contextual LHS calculation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ContextualLHSData:
    """Result of contextual LHS calculation for a specific hour.

    Represents the outcome of calculating average LHS for cycles
    that started at a particular hour of the day.

    Attributes:
        hour: Hour of day (0-23)
        lhs: The calculated LHS value in °C/hour, or None if insufficient data
        cycle_count: Number of cycles used in calculation
        calculated_at: When this calculation was performed
        reason: Human-readable explanation if lhs is None
               (e.g., "insufficient_data", "calculation_failed")
    """

    hour: int
    lhs: float | None
    cycle_count: int
    calculated_at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate the contextual LHS data."""
        if not 0 <= self.hour <= 23:
            raise ValueError(f"hour must be 0-23, got {self.hour}")

        if self.lhs is not None and self.lhs < 0:
            raise ValueError(f"lhs must be positive or None, got {self.lhs}")

        if self.cycle_count < 0:
            raise ValueError(f"cycle_count must be >= 0, got {self.cycle_count}")

    @property
    def is_available(self) -> bool:
        """Check if this hour has valid LHS data."""
        return self.lhs is not None and self.cycle_count > 0

    def get_display_value(self) -> str | float:
        """Get value suitable for user display.

        Returns:
            LHS value as float if available, "unknown" string otherwise.
        """
        if self.lhs is not None:
            return round(self.lhs, 2)
        return "unknown"
