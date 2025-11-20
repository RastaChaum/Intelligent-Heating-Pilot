"""Lagged features value object for ML model."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LaggedFeatures:
    """Represents lagged feature values for thermal inertia encoding.
    
    Captures historical values at specific time lags to encode
    the thermal inertia of the heating system.
    """
    
    # Current room features
    current_temp: float  # Current room temperature (°C)
    target_temp: float  # Target temperature (°C)
    
    # Lagged room temperature (°C)
    temp_lag_15min: float | None
    temp_lag_30min: float | None
    temp_lag_60min: float | None
    temp_lag_90min: float | None
    
    # Lagged heating power state (0=off, 1=on)
    power_lag_15min: float | None
    power_lag_30min: float | None
    power_lag_60min: float | None
    power_lag_90min: float | None
    
    # Environmental features
    outdoor_temp: float | None  # Outdoor temperature (°C)
    humidity: float | None  # Indoor humidity (%)
    
    # Time-of-day features (cyclic encoding)
    hour_sin: float  # sin(2π * hour / 24)
    hour_cos: float  # cos(2π * hour / 24)
    
    # Temperature delta
    temp_delta: float  # target_temp - current_temp
    
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
            "temp_lag_15min": self.temp_lag_15min or 0.0,
            "temp_lag_30min": self.temp_lag_30min or 0.0,
            "temp_lag_60min": self.temp_lag_60min or 0.0,
            "temp_lag_90min": self.temp_lag_90min or 0.0,
            "power_lag_15min": self.power_lag_15min or 0.0,
            "power_lag_30min": self.power_lag_30min or 0.0,
            "power_lag_60min": self.power_lag_60min or 0.0,
            "power_lag_90min": self.power_lag_90min or 0.0,
            "outdoor_temp": self.outdoor_temp or 0.0,
            "humidity": self.humidity or 0.0,
            "hour_sin": self.hour_sin,
            "hour_cos": self.hour_cos,
        }
    
    @staticmethod
    def get_feature_names() -> list[str]:
        """Get ordered list of feature names for ML model.
        
        Returns:
            List of feature names in consistent order.
        """
        return [
            "current_temp",
            "target_temp",
            "temp_delta",
            "temp_lag_15min",
            "temp_lag_30min",
            "temp_lag_60min",
            "temp_lag_90min",
            "power_lag_15min",
            "power_lag_30min",
            "power_lag_60min",
            "power_lag_90min",
            "outdoor_temp",
            "humidity",
            "hour_sin",
            "hour_cos",
        ]
