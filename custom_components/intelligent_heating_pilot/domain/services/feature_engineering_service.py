"""Feature engineering service for ML model."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from ..value_objects import CycleFeatures, HeatingCycle, LaggedFeatures

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
    
    def calculate_aggregated_lagged_values(
        self,
        history: list[tuple[datetime, float]],
        current_time: datetime,
        aggregation_func: str = "avg",
    ) -> dict[int, float | None]:
        """Calculate aggregated lagged values for all lag intervals.
        
        For each lag interval, aggregates all values in the time window
        between the current interval and the previous interval using
        the specified aggregation function.
        
        Args:
            history: List of (timestamp, value) tuples, assumed sorted by time
            current_time: Current timestamp
            aggregation_func: Aggregation function name ("avg", "min", "max", "median")
            
        Returns:
            Dictionary mapping lag_minutes to aggregated value.
            None if insufficient data for that interval.
        """
        if not history:
            return {lag: None for lag in LAG_INTERVALS}
        
        result = {}
        prev_lag = 0
        
        for lag_min in LAG_INTERVALS:
            # Define time window: (current_time - lag_min, current_time - prev_lag]
            window_start = current_time - timedelta(minutes=lag_min)
            window_end = current_time - timedelta(minutes=prev_lag)
            
            # Collect values in this window
            window_values = [
                val for ts, val in history
                if window_start <= ts < window_end
            ]
            
            if not window_values:
                result[lag_min] = None
            else:
                # Apply aggregation function
                if aggregation_func == "avg":
                    result[lag_min] = sum(window_values) / len(window_values)
                elif aggregation_func == "min":
                    result[lag_min] = min(window_values)
                elif aggregation_func == "max":
                    result[lag_min] = max(window_values)
                elif aggregation_func == "median":
                    sorted_vals = sorted(window_values)
                    n = len(sorted_vals)
                    if n % 2 == 0:
                        result[lag_min] = (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2
                    else:
                        result[lag_min] = sorted_vals[n//2]
                else:
                    raise ValueError(f"Unknown aggregation function: {aggregation_func}")
            
            prev_lag = lag_min
        
        return result
    
    def create_lagged_features(
        self,
        current_temp: float,
        target_temp: float,
        current_time: datetime,
        temp_history: list[tuple[datetime, float]],
        slope_history: list[tuple[datetime, float]],
        power_history: list[tuple[datetime, float]],  # Now float (percentage)
        current_slope: float | None = None,
        outdoor_temp: float | None = None,
        humidity: float | None = None,
        cloud_coverage: float | None = None,
        outdoor_temp_history: list[tuple[datetime, float]] | None = None,
        humidity_history: list[tuple[datetime, float]] | None = None,
        cloud_coverage_history: list[tuple[datetime, float]] | None = None,
    ) -> LaggedFeatures:
        """Create lagged features from historical data.
        
        Args:
            current_temp: Current room temperature (°C)
            target_temp: Target temperature (°C)
            current_time: Current timestamp
            temp_history: Temperature history (timestamp, temp) tuples
            power_history: Power state history (timestamp, power_percentage) tuples
            current_slope: Current temperature slope (°C/h)
            outdoor_temp: Current outdoor temperature (°C)
            humidity: Current indoor humidity (%)
            cloud_coverage: Current cloud coverage (%)
            outdoor_temp_history: Outdoor temperature history
            humidity_history: Humidity history
            cloud_coverage_history: Cloud coverage history
            
        Returns:
            LaggedFeatures object with all features calculated.
        """
        # Calculate time-of-day features
        hour_sin, hour_cos = self.calculate_time_of_day_features(current_time)
        
        # Calculate lagged temperature values (average aggregation)
        temp_lags = self.calculate_aggregated_lagged_values(
            temp_history, current_time, aggregation_func="avg"
        )
        
        # Calculate lagged slope values (average aggregation)
        slope_lags = self.calculate_aggregated_lagged_values(
            slope_history, current_time, aggregation_func="avg"
        )

        # Calculate lagged power values (average aggregation)
        power_lags = self.calculate_aggregated_lagged_values(
            power_history, current_time, aggregation_func="avg"
        )
        
        # Calculate lagged outdoor temperature values
        outdoor_temp_lags = {lag: None for lag in LAG_INTERVALS}
        if outdoor_temp_history:
            outdoor_temp_lags = self.calculate_aggregated_lagged_values(
                outdoor_temp_history, current_time, aggregation_func="avg"
            )
        
        # Calculate lagged humidity values
        humidity_lags = {lag: None for lag in LAG_INTERVALS}
        if humidity_history:
            humidity_lags = self.calculate_aggregated_lagged_values(
                humidity_history, current_time, aggregation_func="avg"
            )
        
        # Calculate lagged cloud coverage values
        cloud_coverage_lags = {lag: None for lag in LAG_INTERVALS}
        if cloud_coverage_history:
            cloud_coverage_lags = self.calculate_aggregated_lagged_values(
                cloud_coverage_history, current_time, aggregation_func="avg"
            )
        
        # Calculate temperature delta
        temp_delta = target_temp - current_temp
        
        return LaggedFeatures(
            current_temp=current_temp,
            target_temp=target_temp,
            current_slope=current_slope,
            temp_lag_15min=temp_lags[15],
            temp_lag_30min=temp_lags[30],
            temp_lag_60min=temp_lags[60],
            temp_lag_90min=temp_lags[90],
            temp_lag_120min=temp_lags[120],
            temp_lag_180min=temp_lags[180],
            slope_lag_15min=slope_lags[15],
            slope_lag_30min=slope_lags[30],
            slope_lag_60min=slope_lags[60],
            slope_lag_90min=slope_lags[90],
            slope_lag_120min=slope_lags[120],
            slope_lag_180min=slope_lags[180],
            power_lag_15min=power_lags[15],
            power_lag_30min=power_lags[30],
            power_lag_60min=power_lags[60],
            power_lag_90min=power_lags[90],
            power_lag_120min=power_lags[120],
            power_lag_180min=power_lags[180],
            temp_delta=temp_delta,
        )
    
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
