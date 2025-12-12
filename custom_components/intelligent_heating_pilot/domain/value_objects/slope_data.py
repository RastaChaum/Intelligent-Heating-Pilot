"""Value object for slope data with timestamp.

This value object represents a recorded heating slope measurement
with associated metadata. Designed to be extensible for future ML features.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SlopeData:
    """Immutable record of a heating slope measurement.
    
    Attributes:
        slope_value: Heating slope in °C/hour
        timestamp: UTC timestamp when the slope was recorded
    """
    
    slope_value: float
    timestamp: datetime
    
    def __post_init__(self) -> None:
        """Validate slope data after initialization."""
        if self.slope_value <= 0:
            raise ValueError(f"Slope value must be positive, got {self.slope_value}")
        
        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
