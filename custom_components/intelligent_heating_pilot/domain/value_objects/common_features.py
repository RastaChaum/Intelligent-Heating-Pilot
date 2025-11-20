"""Common features shared across all rooms."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommonFeatures:
    """Common environmental and time features shared by all rooms.
    
    These features represent external conditions that affect all rooms
    equally (weather, time of day). They are shared to avoid duplication
    when modeling multiple rooms simultaneously.
    """
    
    # Current environmental values
    outdoor_temp: float | None  # Outdoor temperature (°C)
    humidity: float | None  # Indoor humidity (%)
    cloud_coverage: float | None  # Cloud coverage (%)
    
    # Lagged environmental features - outdoor temperature (°C)
    outdoor_temp_lag_15min: float | None
    outdoor_temp_lag_30min: float | None
    outdoor_temp_lag_60min: float | None
    outdoor_temp_lag_90min: float | None
    outdoor_temp_lag_120min: float | None
    outdoor_temp_lag_180min: float | None
    
    # Lagged environmental features - humidity (%)
    humidity_lag_15min: float | None
    humidity_lag_30min: float | None
    humidity_lag_60min: float | None
    humidity_lag_90min: float | None
    humidity_lag_120min: float | None
    humidity_lag_180min: float | None
    
    # Lagged environmental features - cloud coverage (%)
    cloud_coverage_lag_15min: float | None
    cloud_coverage_lag_30min: float | None
    cloud_coverage_lag_60min: float | None
    cloud_coverage_lag_90min: float | None
    cloud_coverage_lag_120min: float | None
    cloud_coverage_lag_180min: float | None
    
    # Time-of-day features (cyclic encoding)
    hour_sin: float  # sin(2π * hour / 24)
    hour_cos: float  # cos(2π * hour / 24)
    
    def to_feature_dict(self) -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Returns:
            Dictionary with feature names as keys and values as floats.
            None values are replaced with 0.0.
        """
        return {
            "outdoor_temp": self.outdoor_temp or 0.0,
            "humidity": self.humidity or 0.0,
            "cloud_coverage": self.cloud_coverage or 0.0,
            "outdoor_temp_lag_15min": self.outdoor_temp_lag_15min or 0.0,
            "outdoor_temp_lag_30min": self.outdoor_temp_lag_30min or 0.0,
            "outdoor_temp_lag_60min": self.outdoor_temp_lag_60min or 0.0,
            "outdoor_temp_lag_90min": self.outdoor_temp_lag_90min or 0.0,
            "outdoor_temp_lag_120min": self.outdoor_temp_lag_120min or 0.0,
            "outdoor_temp_lag_180min": self.outdoor_temp_lag_180min or 0.0,
            "humidity_lag_15min": self.humidity_lag_15min or 0.0,
            "humidity_lag_30min": self.humidity_lag_30min or 0.0,
            "humidity_lag_60min": self.humidity_lag_60min or 0.0,
            "humidity_lag_90min": self.humidity_lag_90min or 0.0,
            "humidity_lag_120min": self.humidity_lag_120min or 0.0,
            "humidity_lag_180min": self.humidity_lag_180min or 0.0,
            "cloud_coverage_lag_15min": self.cloud_coverage_lag_15min or 0.0,
            "cloud_coverage_lag_30min": self.cloud_coverage_lag_30min or 0.0,
            "cloud_coverage_lag_60min": self.cloud_coverage_lag_60min or 0.0,
            "cloud_coverage_lag_90min": self.cloud_coverage_lag_90min or 0.0,
            "cloud_coverage_lag_120min": self.cloud_coverage_lag_120min or 0.0,
            "cloud_coverage_lag_180min": self.cloud_coverage_lag_180min or 0.0,
            "hour_sin": self.hour_sin,
            "hour_cos": self.hour_cos,
        }
    
    @staticmethod
    def get_feature_names() -> list[str]:
        """Get ordered list of common feature names.
        
        Returns:
            List of feature names in consistent order.
        """
        return [
            "outdoor_temp",
            "humidity",
            "cloud_coverage",
            "outdoor_temp_lag_15min",
            "outdoor_temp_lag_30min",
            "outdoor_temp_lag_60min",
            "outdoor_temp_lag_90min",
            "outdoor_temp_lag_120min",
            "outdoor_temp_lag_180min",
            "humidity_lag_15min",
            "humidity_lag_30min",
            "humidity_lag_60min",
            "humidity_lag_90min",
            "humidity_lag_120min",
            "humidity_lag_180min",
            "cloud_coverage_lag_15min",
            "cloud_coverage_lag_30min",
            "cloud_coverage_lag_60min",
            "cloud_coverage_lag_90min",
            "cloud_coverage_lag_120min",
            "cloud_coverage_lag_180min",
            "hour_sin",
            "hour_cos",
        ]
