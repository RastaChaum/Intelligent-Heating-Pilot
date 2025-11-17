"""LHS (Learning Heating Slope) calculation service.

This service contains the domain logic for calculating heating slopes
from historical data using robust statistical methods.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..value_objects import SlopeData

_LOGGER = logging.getLogger(__name__)

DEFAULT_HEATING_SLOPE = 2.0  # °C/h - Conservative default


class LHSCalculationService:
    """Service for calculating Learning Heating Slope from historical data.
    
    This service provides domain logic for:
    - Filtering slopes based on time windows (contextual LHS)
    - Calculating robust averages (trimmed mean) from slope values
    - Handling edge cases (insufficient data, empty lists)
    - Providing sensible defaults
    
    All calculations are pure domain logic with no infrastructure dependencies.
    """
    
    def calculate_robust_average(self, slope_values: list[float]) -> float:
        """Calculate robust average by removing extreme values (trimmed mean).
        
        This method provides a more stable estimate by removing outliers.
        Uses a trimmed mean algorithm: removes top and bottom 10% of values.
        
        Args:
            slope_values: List of slope values in °C/hour
            
        Returns:
            Robust average of the values in °C/hour
        """
        if not slope_values:
            _LOGGER.debug(
                "No slope values provided, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Sort values
        sorted_values = sorted(slope_values)
        n = len(sorted_values)
        
        if n < 4:
            # Not enough data for trimming, use simple average
            avg = sum(sorted_values) / n
            _LOGGER.debug(
                "Insufficient data for trimming (%d values), using simple average: %.2f°C/h",
                n,
                avg
            )
            return avg
        
        # Remove top and bottom 10% (trimmed mean)
        trim_count = max(1, int(n * 0.1))
        trimmed = sorted_values[trim_count:-trim_count]
        
        if not trimmed:
            # Fallback to median if trimming removed everything
            median = sorted_values[n // 2]
            _LOGGER.debug(
                "Trimming removed all values, using median: %.2f°C/h",
                median
            )
            return median
        
        avg = sum(trimmed) / len(trimmed)
        _LOGGER.debug(
            "Calculated trimmed mean from %d values (trimmed %d): %.2f°C/h",
            n,
            n - len(trimmed),
            avg
        )
        return avg
    
    def calculate_from_slope_data(self, slope_data_list: list[SlopeData]) -> float:
        """Calculate robust average from SlopeData objects.
        
        Convenience method that extracts slope values from SlopeData objects
        and calculates the robust average.
        
        Args:
            slope_data_list: List of SlopeData objects
            
        Returns:
            Robust average of slope values in °C/hour
        """
        if not slope_data_list:
            _LOGGER.debug(
                "No SlopeData provided, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        slope_values = [sd.slope_value for sd in slope_data_list]
        return self.calculate_robust_average(slope_values)
    
    def calculate_contextual_lhs(
        self,
        all_slope_data: list[SlopeData],
        target_time: datetime,
        window_hours: float
    ) -> float:
        """Calculate LHS from slopes within a time window before target time.
        
        This method implements the core domain logic for contextual LHS:
        - Filters slopes to only those within the time window preceding target_time
        - Calculates robust average from the filtered slopes
        - Represents environmental conditions (solar gain, etc.) for that period
        
        Args:
            all_slope_data: All available slope data (will be filtered)
            target_time: Target time for which to calculate LHS
            window_hours: Size of time window in hours before target_time
            
        Returns:
            Contextual LHS in °C/hour based on time-windowed slopes
        """
        if not all_slope_data:
            _LOGGER.debug(
                "No slope data available for contextual LHS, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Calculate window start time
        window_start = target_time - timedelta(hours=window_hours)
        
        # Filter slopes within the time window
        window_slopes = [
            sd for sd in all_slope_data
            if window_start <= sd.timestamp < target_time
        ]
        
        if not window_slopes:
            _LOGGER.debug(
                "No slopes found in %.1fh window before %s, using default: %.2f°C/h",
                window_hours,
                target_time.isoformat(),
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Calculate LHS from window slopes
        lhs = self.calculate_from_slope_data(window_slopes)
        
        _LOGGER.info(
            "Calculated contextual LHS from %d slopes in %.1fh window (before %s): %.2f°C/h",
            len(window_slopes),
            window_hours,
            target_time.isoformat(),
            lhs
        )
        
        return lhs
