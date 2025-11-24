"""Cycle features value object for ML model."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CycleFeatures:
    """Represents features available at the start of a heating cycle.
    
    Contains only data that is available at the moment the heating cycle
    begins, avoiding any forward-looking data leakage.
    """
    
    # Temperature features
    current_temp: float  # Current room temperature at cycle start (°C)
    target_temp: float  # Target temperature (°C)
    temp_delta: float  # target_temp - current_temp (°C)
    
    # Thermal dynamics
    current_slope: float | None  # Current temperature slope (°C/h)
    
    # Environmental features
    outdoor_temp: float | None  # Outdoor temperature at cycle start (°C)
    outdoor_humidity: float | None  # Outdoor humidity at cycle start (%)
    humidity: float | None  # Indoor humidity at cycle start (%)
    cloud_coverage: float | None  # Cloud coverage at cycle start (%)
    
    def to_feature_dict(self) -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Returns:
            Dictionary with feature names as keys and values as floats.
            None values are replaced with 0.0.
        """
        return {
            "current_temp": self.current_temp,
            "target_temp": self.target_temp,
            "temp_delta": self.temp_delta,
            "current_slope": self.current_slope or 0.0,
            "outdoor_temp": self.outdoor_temp or 0.0,
            "outdoor_humidity": self.outdoor_humidity or 0.0,
            "humidity": self.humidity or 0.0,
            "cloud_coverage": self.cloud_coverage or 0.0,
        }

    @classmethod
    def get_feature_names(cls) -> list[str]:
        """Get ordered list of feature names for ML model.
        
        Returns:
            List of feature names in the order they should be used.
        """
        return [
            "current_temp",
            "target_temp",
            "temp_delta",
            "current_slope",
            "outdoor_temp",
            "outdoor_humidity",
            "humidity",
            "cloud_coverage",
        ]
