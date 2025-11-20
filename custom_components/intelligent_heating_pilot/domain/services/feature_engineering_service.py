"""Feature engineering service for ML model."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from ..value_objects import LaggedFeatures

_LOGGER = logging.getLogger(__name__)

# Lag intervals in minutes
LAG_INTERVALS = [15, 30, 60, 90]


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
    
    def calculate_lagged_value(
        self,
        history: list[tuple[datetime, float]],
        current_time: datetime,
        lag_minutes: int,
    ) -> float | None:
        """Calculate lagged value from historical time series.
        
        Uses linear interpolation to estimate value at lagged timestamp.
        
        Args:
            history: List of (timestamp, value) tuples, assumed sorted by time
            current_time: Current timestamp
            lag_minutes: How many minutes to look back
            
        Returns:
            Interpolated value at lagged time, or None if insufficient history.
        """
        if not history:
            return None
        
        target_time = current_time - timedelta(minutes=lag_minutes)
        
        # Find the two points to interpolate between
        before_point = None
        after_point = None
        
        for ts, val in history:
            if ts <= target_time:
                before_point = (ts, val)
            elif ts > target_time and after_point is None:
                after_point = (ts, val)
                break
        
        # Check if we have data at exactly the target time
        if before_point and before_point[0] == target_time:
            return before_point[1]
        
        # Check if we can interpolate
        if before_point is None or after_point is None:
            # Not enough history to calculate lag
            return None
        
        # Linear interpolation
        t0, v0 = before_point
        t1, v1 = after_point
        
        total_seconds = (t1 - t0).total_seconds()
        if total_seconds == 0:
            return v0
        
        ratio = (target_time - t0).total_seconds() / total_seconds
        interpolated = v0 + ratio * (v1 - v0)
        
        return interpolated
    
    def calculate_power_lagged_value(
        self,
        power_history: list[tuple[datetime, bool]],
        current_time: datetime,
        lag_minutes: int,
    ) -> float | None:
        """Calculate lagged power state value (0 or 1).
        
        Args:
            power_history: List of (timestamp, is_heating) tuples
            current_time: Current timestamp
            lag_minutes: How many minutes to look back
            
        Returns:
            1.0 if heating was on at lagged time, 0.0 if off, None if no data.
        """
        if not power_history:
            return None
        
        target_time = current_time - timedelta(minutes=lag_minutes)
        
        # Find the most recent state before or at target time
        for ts, is_heating in reversed(power_history):
            if ts <= target_time:
                return 1.0 if is_heating else 0.0
        
        # No data before target time
        return None
    
    def create_lagged_features(
        self,
        current_temp: float,
        target_temp: float,
        current_time: datetime,
        temp_history: list[tuple[datetime, float]],
        power_history: list[tuple[datetime, bool]],
        outdoor_temp: float | None = None,
        humidity: float | None = None,
    ) -> LaggedFeatures:
        """Create lagged features from historical data.
        
        Args:
            current_temp: Current room temperature (°C)
            target_temp: Target temperature (°C)
            current_time: Current timestamp
            temp_history: Temperature history (timestamp, temp) tuples
            power_history: Power state history (timestamp, is_heating) tuples
            outdoor_temp: Outdoor temperature (°C)
            humidity: Indoor humidity (%)
            
        Returns:
            LaggedFeatures object with all features calculated.
        """
        # Calculate time-of-day features
        hour_sin, hour_cos = self.calculate_time_of_day_features(current_time)
        
        # Calculate lagged temperature values
        temp_lags = {}
        for lag_min in LAG_INTERVALS:
            lag_val = self.calculate_lagged_value(temp_history, current_time, lag_min)
            temp_lags[lag_min] = lag_val
        
        # Calculate lagged power values
        power_lags = {}
        for lag_min in LAG_INTERVALS:
            lag_val = self.calculate_power_lagged_value(
                power_history, current_time, lag_min
            )
            power_lags[lag_min] = lag_val
        
        # Calculate temperature delta
        temp_delta = target_temp - current_temp
        
        return LaggedFeatures(
            current_temp=current_temp,
            target_temp=target_temp,
            temp_lag_15min=temp_lags[15],
            temp_lag_30min=temp_lags[30],
            temp_lag_60min=temp_lags[60],
            temp_lag_90min=temp_lags[90],
            power_lag_15min=power_lags[15],
            power_lag_30min=power_lags[30],
            power_lag_60min=power_lags[60],
            power_lag_90min=power_lags[90],
            outdoor_temp=outdoor_temp,
            humidity=humidity,
            hour_sin=hour_sin,
            hour_cos=hour_cos,
            temp_delta=temp_delta,
        )
