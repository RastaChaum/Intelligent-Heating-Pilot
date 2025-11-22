"""Heating cycle value object."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class HeatingCycle:
    """Represents a complete heating cycle for ML training.
    
    A heating cycle is defined as a period where:
    - The thermostat is in "heat" mode
    - Room temperature is at least 0.3°C below target temperature
    
    The cycle captures environmental conditions at start and end
    for model learning, independent of any scheduling system.
    """
    
    climate_entity_id: str  # Identifier for the climate entity
    
    # Timing information
    cycle_start: datetime  # When heating cycle started
    cycle_end: datetime  # When heating cycle ended
    duration_minutes: float  # Cycle duration in minutes
    
    # Temperature information
    initial_temp: float  # Temperature at cycle start (°C)
    target_temp: float  # Target temperature during cycle (°C)
    final_temp: float  # Temperature at cycle end (°C)
    
    # Slope information (temperature rate of change in °C/h)
    initial_slope: float | None  # Temperature slope at start
    final_slope: float | None  # Temperature slope at end
    
    # Humidity information (%)
    initial_humidity: float | None  # Humidity at cycle start
    final_humidity: float | None  # Humidity at cycle end
    
    # Environmental data at cycle start
    initial_outdoor_temp: float | None  # Outdoor temperature at start (°C)
    initial_outdoor_humidity: float | None  # Outdoor humidity at start (%)
    initial_cloud_coverage: float | None  # Cloud coverage at start (%)
    
    # Environmental data at cycle end
    final_outdoor_temp: float | None  # Outdoor temperature at end (°C)
    final_outdoor_humidity: float | None  # Outdoor humidity at end (%)
    final_cloud_coverage: float | None  # Cloud coverage at end (%)
    
    # Auto-generated unique identifier (UUID)
    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def __post_init__(self) -> None:
        """Validate heating cycle data."""
        if self.duration_minutes < 0:
            raise ValueError("duration_minutes cannot be negative")
        if self.initial_temp > self.target_temp:
            raise ValueError("initial_temp must be below target_temp for a valid heating cycle")
