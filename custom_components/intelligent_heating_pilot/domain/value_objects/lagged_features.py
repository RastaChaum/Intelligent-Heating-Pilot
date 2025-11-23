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
    current_slope: float | None  # Current temperature slope (°C/h)
    
    # Lagged room temperature (°C)
    temp_lag_15min: float | None
    temp_lag_30min: float | None
    temp_lag_60min: float | None
    temp_lag_90min: float | None
    temp_lag_120min: float | None
    temp_lag_180min: float | None
    
    # Lagged slopeed features -
    slope_lag_15min: float | None
    slope_lag_30min: float | None
    slope_lag_60min: float | None
    slope_lag_90min: float | None
    slope_lag_120min: float | None
    slope_lag_180min: float | None

    # Lagged heating power state (0=off, 1=on)
    power_lag_15min: float | None
    power_lag_30min: float | None
    power_lag_60min: float | None
    power_lag_90min: float | None
    power_lag_120min: float | None
    power_lag_180min: float | None
    
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
            "current_slope": self.current_slope or 0.0,
            "temp_lag_15min": self.temp_lag_15min or 0.0,
            "temp_lag_30min": self.temp_lag_30min or 0.0,
            "temp_lag_60min": self.temp_lag_60min or 0.0,
            "temp_lag_90min": self.temp_lag_90min or 0.0,
            "temp_lag_120min": self.temp_lag_120min or 0.0,
            "temp_lag_180min": self.temp_lag_180min or 0.0,
            "slope_lag_15min": self.slope_lag_15min or 0.0,
            "slope_lag_30min": self.slope_lag_30min or 0.0,
            "slope_lag_60min": self.slope_lag_60min or 0.0,
            "slope_lag_90min": self.slope_lag_90min or 0.0,
            "slope_lag_120min": self.slope_lag_120min or 0.0,
            "slope_lag_180min": self.slope_lag_180min or 0.0,
            "power_lag_15min": self.power_lag_15min or 0.0,
            "power_lag_30min": self.power_lag_30min or 0.0,
            "power_lag_60min": self.power_lag_60min or 0.0,
            "power_lag_90min": self.power_lag_90min or 0.0,
            "power_lag_120min": self.power_lag_120min or 0.0,
            "power_lag_180min": self.power_lag_180min or 0.0,
        }

    @classmethod
    def get_feature_names(cls) -> list[str]:
        """Get ordered list of feature names for ML model.
        
        Returns:
            List of feature names in the order they should be used.
        """
        return ["current_temp",
            "target_temp",
            "temp_delta",
            "current_slope",
            "temp_lag_15min",
            "temp_lag_30min",
            "temp_lag_60min",
            "temp_lag_90min",
            "temp_lag_120min",
            "temp_lag_180min",
            "slope_lag_15min",
            "slope_lag_30min",
            "slope_lag_60min",
            "slope_lag_90min",
            "slope_lag_120min",
            "slope_lag_180min",
            "power_lag_15min",
            "power_lag_30min",
            "power_lag_60min",
            "power_lag_90min",
            "power_lag_120min",
            "power_lag_180min",
        ]