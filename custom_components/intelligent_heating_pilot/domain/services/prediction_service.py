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
    
    The calculation considers:
    1. Temperature difference to heat
    2. Outdoor temperature impact on heat loss
    3. Humidity effects on heating efficiency
    4. Solar gain from cloud coverage
    5. Learned heating slope (heating rate) from historical data
    """
    
    # Constants for calculation
    DEFAULT_ANTICIPATION_BUFFER = 5  # minutes - Safety buffer
    MIN_ANTICIPATION_TIME = 10  # minutes - Minimum anticipation
    MAX_ANTICIPATION_TIME = 180  # minutes (3 hours) - Maximum anticipation
    
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
            humidity: Indoor humidity percentage (0-100)
            cloud_coverage: Cloud coverage percentage (0-100, 0=clear sky)
            
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
        
        # Apply environmental correction factors
        correction_factor = self._calculate_environmental_correction(
            outdoor_temp, humidity, cloud_coverage
        )
        
        anticipation_minutes *= correction_factor
        
        # Apply buffer and limits
        anticipation_minutes += self.DEFAULT_ANTICIPATION_BUFFER
        anticipation_minutes = max(
            self.MIN_ANTICIPATION_TIME,
            min(self.MAX_ANTICIPATION_TIME, anticipation_minutes)
        )
        
        # Calculate anticipated start time
        anticipated_start = target_time - timedelta(minutes=anticipation_minutes)
        
        # Calculate confidence level based on slope and available environmental data
        confidence = self._calculate_confidence(learned_slope, outdoor_temp, humidity)
        
        _LOGGER.debug(
            "Prediction: ΔT=%.1f°C, slope=%.2f°C/h, correction=%.2f, "
            "duration=%.1f min, confidence=%.2f",
            temp_delta,
            learned_slope,
            correction_factor,
            anticipation_minutes,
            confidence
        )
        
        return PredictionResult(
            anticipated_start_time=anticipated_start,
            estimated_duration_minutes=anticipation_minutes,
            confidence_level=confidence,
            learned_heating_slope=learned_slope,
        )
    
    def _calculate_environmental_correction(
        self,
        outdoor_temp: float | None,
        humidity: float | None,
        cloud_coverage: float | None,
    ) -> float:
        """Calculate combined environmental correction factor.
        
        This method combines multiple environmental factors that affect
        heating efficiency:
        - Outdoor temperature (heat loss)
        - Indoor humidity (thermal mass effect)
        - Cloud coverage (solar gain)
        
        Args:
            outdoor_temp: Outdoor temperature in Celsius
            humidity: Indoor humidity percentage (0-100)
            cloud_coverage: Cloud coverage percentage (0-100)
            
        Returns:
            Combined correction factor (>1 means slower heating)
        """
        correction_factor = 1.0
        
        # Outdoor temperature factor: colder outside means slower heating
        # Formula: outdoor_factor = 1 + (20 - outdoor_temp) * 0.05
        # At outdoor_temp = 20°C: factor = 1.0 (no impact)
        # At outdoor_temp = 0°C: factor = 2.0 (heating takes twice as long)
        # At outdoor_temp = -10°C: factor = 2.5 (even slower)
        if outdoor_temp is not None:
            outdoor_factor = 1.0 + (20.0 - outdoor_temp) * 0.05
            outdoor_factor = max(0.5, outdoor_factor)  # Minimum factor of 0.5
            correction_factor *= outdoor_factor
            _LOGGER.debug("Outdoor temp %.1f°C -> factor %.2f", outdoor_temp, outdoor_factor)
        
        # Humidity factor: higher humidity makes heating feel slower
        # Formula: humidity_factor = 1 + (humidity - 50) * 0.002
        # At 50% humidity: factor = 1.0 (neutral)
        # At 80% humidity: factor = 1.06 (6% slower)
        # At 20% humidity: factor = 0.94 (6% faster)
        if humidity is not None:
            humidity_factor = 1.0 + (humidity - 50.0) * 0.002
            humidity_factor = max(0.8, min(1.2, humidity_factor))
            correction_factor *= humidity_factor
            _LOGGER.debug("Humidity %.1f%% -> factor %.2f", humidity, humidity_factor)
        
        # Solar gain factor: less cloud coverage means more solar heat gain
        # Formula: solar_factor = 1 - (100 - cloud_coverage) * 0.001
        # At 100% cloud: factor = 1.0 (no solar gain)
        # At 0% cloud (clear sky): factor = 0.9 (10% faster due to sun)
        # At 50% cloud: factor = 0.95 (5% faster)
        if cloud_coverage is not None:
            solar_factor = 1.0 - (100.0 - cloud_coverage) * 0.001
            solar_factor = max(0.8, min(1.0, solar_factor))
            correction_factor *= solar_factor
            _LOGGER.debug("Cloud coverage %.1f%% -> factor %.2f", cloud_coverage, solar_factor)
        
        return correction_factor
    
    def _calculate_confidence(
        self,
        learned_slope: float,
        outdoor_temp: float | None,
        humidity: float | None,
    ) -> float:
        """Calculate confidence level in the prediction.
        
        Confidence is based on:
        - Slope validity (higher slope = better learning)
        - Available environmental data (more data = better prediction)
        
        Args:
            learned_slope: Learned heating slope in °C/hour
            outdoor_temp: Outdoor temperature (if available)
            humidity: Indoor humidity (if available)
            
        Returns:
            Confidence level between 0.0 and 1.0
        """
        # Base confidence from slope validity
        if learned_slope > 1.5:
            confidence = 0.9  # High confidence with good slope
        elif learned_slope > 0.5:
            confidence = 0.75  # Medium confidence
        else:
            confidence = 0.6  # Lower confidence with low slope
        
        # Adjust confidence based on available environmental data
        data_availability = 0
        if outdoor_temp is not None:
            data_availability += 1
        if humidity is not None:
            data_availability += 1
        
        # Increase confidence slightly with more environmental data
        confidence += data_availability * 0.05
        
        # Cap at 1.0
        return min(1.0, confidence)
