"""Heating cycle value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HeatingCycle:
    """Represents a complete heating cycle for ML training.
    
    A heating cycle captures a historical heating event with all
    relevant data for training the prediction model.
    """
    
    cycle_id: str  # Unique identifier for the cycle
    climate_entity_id: str  # Identifier for the climate entity (room)
    
    # Timing information
    heating_started_at: datetime  # When heating actually started
    target_time: datetime  # When target temperature was supposed to be reached
    real_target_time: datetime | None  # When target was actually reached (None if not reached)
    
    # Temperature information
    initial_temp: float  # Temperature when heating started (°C)
    target_temp: float  # Target temperature (°C)
    final_temp: float  # Temperature at target_time (°C)
       
    # Calculated values
    actual_duration_minutes: float  # How long heating actually took
    optimal_duration_minutes: float  # Calculated optimal duration based on error
    error_minutes: float  # target_reached_at - target_time in minutes (+ is late, - is early)
    
    def __post_init__(self) -> None:
        """Validate heating cycle data."""
        if self.actual_duration_minutes < 0:
            raise ValueError("actual_duration_minutes cannot be negative")
        if self.optimal_duration_minutes < 0:
            raise ValueError("optimal_duration_minutes cannot be negative")
