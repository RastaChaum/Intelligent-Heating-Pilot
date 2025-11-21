"""Heating cycle value object."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class HeatingCycle:
    """Represents a complete heating cycle for ML training.
    
    A heating cycle captures a historical heating event with all
    relevant data for training the prediction model.
    """
    
    climate_entity_id: str  # Identifier for the IHP device (unique device ID)
    
    # Timing information
    heating_started_at: datetime  # When heating actually started
    target_time: datetime  # When target temperature was supposed to be reached
    target_reached_at: datetime | None  # When target was actually reached (None if not reached)
    
    # Temperature information
    initial_temp: float  # Temperature when heating started (°C)
    target_temp: float  # Target temperature (°C)
    final_temp: float  # Temperature at target_time (°C)
    initial_slope: float | None  # Temperature slope at start (°C/h)
      
    # Calculated values
    actual_duration_minutes: float  # How long heating actually took
    optimal_duration_minutes: float  # Calculated optimal duration based on error
    error_minutes: float  # target_reached_at - target_time in minutes (+ is late, - is early)
    
    # Auto-generated unique identifier (UUID)
    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def __post_init__(self) -> None:
        """Validate heating cycle data."""
        if self.actual_duration_minutes < 0:
            raise ValueError("actual_duration_minutes cannot be negative")
        if self.optimal_duration_minutes < 0:
            raise ValueError("optimal_duration_minutes cannot be negative")
