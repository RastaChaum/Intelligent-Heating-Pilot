"""Environment state value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EnvironmentState:
    """Represents current environmental conditions.
    
    This value object captures all environmental factors that influence
    heating decisions at a specific point in time.
    
    Attributes:
        indoor_temperature: Current room temperature in Celsius
        timestamp: When these measurements were taken
        indoor_humidity: Indoor humidity percentage (0-100)
        outdoor_temp: Outdoor temperature in Celsius
        outdoor_humidity: Optional outdoor humidity percentage (0-100)
        cloud_coverage: Optional cloud coverage percentage (0-100, 0=clear sky)
    """
    
    indoor_temperature: float
    timestamp: datetime
    indoor_humidity: float | None = None
    outdoor_temp: float | None = None
    outdoor_humidity: float | None = None
    cloud_coverage: float | None = None

    
    def __post_init__(self) -> None:
        """Validate the environmental state data."""
        if self.indoor_humidity is not None and (self.indoor_humidity < 0 or self.indoor_humidity > 100):
            raise ValueError(f"Humidity must be between 0 and 100, got {self.indoor_humidity}")
        
        if self.outdoor_humidity is not None and (
            self.outdoor_humidity < 0 or self.outdoor_humidity > 100
        ):
            raise ValueError(
                f"Outdoor humidity must be between 0 and 100, got {self.outdoor_humidity}"
            )
        
        if self.cloud_coverage is not None and (
            self.cloud_coverage < 0 or self.cloud_coverage > 100
        ):
            raise ValueError(
                f"Cloud coverage must be between 0 and 100, got {self.cloud_coverage}"
            )