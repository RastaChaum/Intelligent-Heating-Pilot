"""Room-specific features for ML model."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoomFeatures:
    """Room-specific thermal features.
    
    These features are unique to each individual room and capture
    its specific thermal behavior and state.
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
    
    # Lagged heating power state (0=off, 1=on)
    power_lag_15min: float | None
    power_lag_30min: float | None
    power_lag_60min: float | None
    power_lag_90min: float | None
    power_lag_120min: float | None
    power_lag_180min: float | None
    
    # Temperature delta
    temp_delta: float  # target_temp - current_temp
    
    def to_feature_dict(self, prefix: str = "") -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Args:
            prefix: Optional prefix for feature names (e.g., "room1_" for adjacent rooms)
        
        Returns:
            Dictionary with feature names as keys and values as floats.
            None values are replaced with 0.0.
        """
        return {
            f"{prefix}current_temp": self.current_temp,
            f"{prefix}target_temp": self.target_temp,
            f"{prefix}temp_delta": self.temp_delta,
            f"{prefix}current_slope": self.current_slope or 0.0,
            f"{prefix}temp_lag_15min": self.temp_lag_15min or 0.0,
            f"{prefix}temp_lag_30min": self.temp_lag_30min or 0.0,
            f"{prefix}temp_lag_60min": self.temp_lag_60min or 0.0,
            f"{prefix}temp_lag_90min": self.temp_lag_90min or 0.0,
            f"{prefix}temp_lag_120min": self.temp_lag_120min or 0.0,
            f"{prefix}temp_lag_180min": self.temp_lag_180min or 0.0,
            f"{prefix}power_lag_15min": self.power_lag_15min or 0.0,
            f"{prefix}power_lag_30min": self.power_lag_30min or 0.0,
            f"{prefix}power_lag_60min": self.power_lag_60min or 0.0,
            f"{prefix}power_lag_90min": self.power_lag_90min or 0.0,
            f"{prefix}power_lag_120min": self.power_lag_120min or 0.0,
            f"{prefix}power_lag_180min": self.power_lag_180min or 0.0,
        }
    
    @staticmethod
    def get_feature_names(prefix: str = "") -> list[str]:
        """Get ordered list of room feature names.
        
        Args:
            prefix: Optional prefix for feature names
        
        Returns:
            List of feature names in consistent order.
        """
        return [
            f"{prefix}current_temp",
            f"{prefix}target_temp",
            f"{prefix}temp_delta",
            f"{prefix}current_slope",
            f"{prefix}temp_lag_15min",
            f"{prefix}temp_lag_30min",
            f"{prefix}temp_lag_60min",
            f"{prefix}temp_lag_90min",
            f"{prefix}temp_lag_120min",
            f"{prefix}temp_lag_180min",
            f"{prefix}power_lag_15min",
            f"{prefix}power_lag_30min",
            f"{prefix}power_lag_60min",
            f"{prefix}power_lag_90min",
            f"{prefix}power_lag_120min",
            f"{prefix}power_lag_180min",
        ]
