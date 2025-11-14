"""Prediction service for calculating heating times."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..value_objects import PredictionResult

_LOGGER = logging.getLogger(__name__)


class PredictionService:
    """Service for predicting heating start times.
    
    This service contains the core prediction algorithm that determines
    when heating should start to reach target temperature at a scheduled time.
    """
    
    # Constants for calculation
    DEFAULT_ANTICIPATION_BUFFER = 5  # minutes
    MIN_ANTICIPATION_TIME = 10  # minutes
    MAX_ANTICIPATION_TIME = 180  # minutes (3 hours)
    
    def predict_heating_time(
        self,
        current_temp: float,
        target_temp: float,
        learned_slope: float,
        target_time: datetime,
        outdoor_temp: float | None = None,
        humidity: float | None = None,
        cloud_coverage: float | None = None,
    ) -> PredictionResult:
        """Calculate when heating should start.
        
        Required Args:
            current_temp: Current room temperature in Celsius
            target_temp: Target temperature in Celsius
            learned_slope: Learned heating slope in °C/hour
            target_time: When target should be reached (mandatory)
            
        Optional Args:
            outdoor_temp: Outdoor temperature in Celsius
            humidity: Indoor humidity percentage
            cloud_coverage: Cloud coverage percentage (0-100)
            
        Returns:
            Prediction result with start time and confidence
        """
        # Calculate temperature difference
        temp_delta = target_temp - current_temp
        
        if temp_delta <= 0:
            # Already at target, anticipated start time = target time
            _LOGGER.debug(
                "Already at target temperature (%.1f°C >= %.1f°C), no heating needed",
                current_temp,
                target_temp
            )
            return PredictionResult(
                anticipated_start_time=target_time,
                estimated_duration_minutes=0.0,
                confidence_level=1.0,
                learned_heating_slope=learned_slope,
            )
        
        # Protection against invalid slope
        if learned_slope <= 0:
            _LOGGER.warning(
                "Invalid learned heating slope (%.2f°C/h <= 0), cannot calculate prediction",
                learned_slope
            )
            return PredictionResult(
                anticipated_start_time=target_time,
                estimated_duration_minutes=0.0,
                confidence_level=0.0,
                learned_heating_slope=learned_slope,
            )
        
        # Calculate base anticipation time (in minutes)
        anticipation_minutes = (temp_delta / learned_slope) * 60.0
        
        # Apply correction factors
        correction_factor = 1.0
        
        # Humidity correction (high humidity = slower heating)
        if humidity is not None and humidity > 70:
            correction_factor *= 1.1
        
        # Cloud coverage correction (no sun = slower heating)
        if cloud_coverage is not None and cloud_coverage > 80:
            correction_factor *= 1.05
        
        anticipation_minutes *= correction_factor
        
        # Apply buffer and limits
        anticipation_minutes += self.DEFAULT_ANTICIPATION_BUFFER
        anticipation_minutes = max(
            self.MIN_ANTICIPATION_TIME,
            min(self.MAX_ANTICIPATION_TIME, anticipation_minutes)
        )
        
        # Calculate anticipated start time
        anticipated_start = target_time - timedelta(minutes=anticipation_minutes)
        
        # Calculate confidence level (higher with more samples would be ideal)
        # For now, use a simple heuristic based on slope validity
        confidence = 0.8 if learned_slope > 0.5 else 0.6
        
        return PredictionResult(
            anticipated_start_time=anticipated_start,
            estimated_duration_minutes=anticipation_minutes,
            confidence_level=confidence,
            learned_heating_slope=learned_slope,
        )
