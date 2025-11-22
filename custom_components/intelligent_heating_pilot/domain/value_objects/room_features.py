"""Room-specific features for ML model."""
from __future__ import annotations

from dataclasses import dataclass

from .lagged_features import LaggedFeatures


@dataclass(frozen=True)
class RoomFeatures:
    """Room-specific thermal features.
    
    These features are unique to each individual room and capture
    its specific thermal behavior and state.
    """
    
    lagged_features: LaggedFeatures  # Lagged features for the specific room 
        
    def to_feature_dict(self, prefix: str = "") -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Args:
            prefix: Optional prefix for feature names (e.g., "room1_" for adjacent rooms)
        
        Returns:
            Dictionary with feature names as keys and values as floats.
            None values are replaced with 0.0.
        """
        return {
            f"{prefix}current_temp": self.lagged_features.current_temp,
            f"{prefix}target_temp": self.lagged_features.target_temp,
            f"{prefix}temp_delta": self.lagged_features.temp_delta,
            f"{prefix}current_slope": self.lagged_features.current_slope or 0.0,
            f"{prefix}slope_lag_15min": self.lagged_features.slope_lag_15min or 0.0,
            f"{prefix}slope_lag_30min": self.lagged_features.slope_lag_30min or 0.0,
            f"{prefix}slope_lag_60min": self.lagged_features.slope_lag_60min or 0.0,
            f"{prefix}slope_lag_90min": self.lagged_features.slope_lag_90min or 0.0,
            f"{prefix}slope_lag_120min": self.lagged_features.slope_lag_120min or 0.0,
            f"{prefix}slope_lag_180min": self.lagged_features.slope_lag_180min or 0.0,
            f"{prefix}temp_lag_15min": self.lagged_features.temp_lag_15min or 0.0,
            f"{prefix}temp_lag_30min": self.lagged_features.temp_lag_30min or 0.0,
            f"{prefix}temp_lag_60min": self.lagged_features.temp_lag_60min or 0.0,
            f"{prefix}temp_lag_90min": self.lagged_features.temp_lag_90min or 0.0,
            f"{prefix}temp_lag_120min": self.lagged_features.temp_lag_120min or 0.0,
            f"{prefix}temp_lag_180min": self.lagged_features.temp_lag_180min or 0.0,
            f"{prefix}power_lag_15min": self.lagged_features.power_lag_15min or 0.0,
            f"{prefix}power_lag_30min": self.lagged_features.power_lag_30min or 0.0,
            f"{prefix}power_lag_60min": self.lagged_features.power_lag_60min or 0.0,
            f"{prefix}power_lag_90min": self.lagged_features.power_lag_90min or 0.0,
            f"{prefix}power_lag_120min": self.lagged_features.power_lag_120min or 0.0,
            f"{prefix}power_lag_180min": self.lagged_features.power_lag_180min or 0.0,
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
            f"{prefix}slope_lag_15min",
            f"{prefix}slope_lag_30min",
            f"{prefix}slope_lag_60min",
            f"{prefix}slope_lag_90min",
            f"{prefix}slope_lag_120min",
            f"{prefix}slope_lag_180min",
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
