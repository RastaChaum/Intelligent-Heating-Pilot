"""Feature engineering service for ML model."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from ..value_objects import CycleFeatures, HeatingCycle

_LOGGER = logging.getLogger(__name__)

# Lag intervals in minutes
LAG_INTERVALS = [15, 30, 60, 90, 120, 180]


class FeatureEngineeringService:
    """Service for engineering features from raw time-series data.
    
    This service contains pure domain logic for transforming raw sensor
    data into features suitable for ML model training and prediction.
    Handles lagged features for thermal inertia encoding.
    """
    
    def calculate_time_of_day_features(self, timestamp: datetime) -> tuple[float, float]:
        """Calculate cyclic time-of-day encoding using sine and cosine.
        
        Encodes the hour of day as a circular feature to capture daily patterns.
        Uses sin/cos to avoid discontinuity at midnight (23:59 -> 00:00).
        
        Args:
            timestamp: The timestamp to encode
            
        Returns:
            Tuple of (hour_sin, hour_cos) representing cyclic hour encoding.
        """
        hour = timestamp.hour + timestamp.minute / 60.0
        # Convert to radians for full circle (0-24 hours -> 0-2π)
        angle = 2 * math.pi * hour / 24.0
        
        hour_sin = math.sin(angle)
        hour_cos = math.cos(angle)
        
        return hour_sin, hour_cos
    

    
    def create_cycle_features(self, cycle: HeatingCycle) -> CycleFeatures:
        """Create features from heating cycle data available at cycle start.
        
        This method extracts only the data that would be available at the
        beginning of the heating cycle, preventing any forward-looking data leakage.
        
        Args:
            cycle: The heating cycle containing initial conditions
            
        Returns:
            CycleFeatures object with features available at cycle start.
        """
        # Calculate temperature delta
        temp_delta = cycle.target_temp - cycle.initial_temp
        
        return CycleFeatures(
            current_temp=cycle.initial_temp,
            target_temp=cycle.target_temp,
            temp_delta=temp_delta,
            current_slope=cycle.initial_slope,
            outdoor_temp=cycle.initial_outdoor_temp,
            outdoor_humidity=cycle.initial_outdoor_humidity,
            humidity=cycle.initial_humidity,
            cloud_coverage=cycle.initial_cloud_coverage,
        )
