"""Prediction result value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PredictionResult:
    """Result of heating time prediction.
    
    Represents when heating should start to reach the target temperature
    at the scheduled time.
    
    Attributes:
        anticipated_start_time: When heating should begin
        estimated_duration_minutes: How long heating is expected to take
        confidence_level: Confidence in prediction (0.0-1.0)
        learned_heating_slope: The heating slope used for prediction (°C/h)
    """
    
    anticipated_start_time: datetime
    estimated_duration_minutes: float
    confidence_level: float
    learned_heating_slope: float
    
    def __post_init__(self) -> None:
        """Validate the prediction result data."""
        if self.estimated_duration_minutes < 0:
            raise ValueError(
                f"Duration must be non-negative, got {self.estimated_duration_minutes}"
            )
        
        if not 0.0 <= self.confidence_level <= 1.0:
            raise ValueError(
                f"Confidence must be between 0 and 1, got {self.confidence_level}"
            )
        
        if self.learned_heating_slope <= 0:
            raise ValueError(
                f"Heating slope must be positive, got {self.learned_heating_slope}"
            )
