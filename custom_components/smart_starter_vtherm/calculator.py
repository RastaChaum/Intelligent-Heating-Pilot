"""Calculation logic for Smart Starter VTherm."""
from datetime import datetime, timedelta
import logging

_LOGGER = logging.getLogger(__name__)


class PreheatingCalculator:
    """Calculate optimal preheating start time."""

    def __init__(self, thermal_slope: float = 2.0):
        """Initialize the calculator.
        
        Args:
            thermal_slope: Heating rate in degrees Celsius per hour.
                          This represents how fast the room heats up.
        """
        self.thermal_slope = thermal_slope

    def calculate_preheat_duration(
        self,
        current_temp: float,
        target_temp: float,
        outdoor_temp: float,
    ) -> float:
        """Calculate the preheating duration in minutes.
        
        Args:
            current_temp: Current room temperature in Celsius
            target_temp: Target temperature in Celsius
            outdoor_temp: Outdoor temperature in Celsius
            
        Returns:
            Preheating duration in minutes
            
        The calculation considers:
        1. Temperature difference to heat
        2. Outdoor temperature impact on heat loss
        3. Thermal slope (heating rate) of the room
        """
        # If already at or above target, no preheating needed
        if current_temp >= target_temp:
            _LOGGER.debug(
                "Current temp %.1f°C already at or above target %.1f°C",
                current_temp,
                target_temp,
            )
            return 0.0

        # Temperature difference to achieve
        temp_delta = target_temp - current_temp

        # Outdoor temperature factor: colder outside means slower heating
        # and more heat loss. This reduces effective heating rate.
        # Formula: outdoor_factor = 1 + (20 - outdoor_temp) * 0.05
        # At outdoor_temp = 20°C: factor = 1.0 (no impact)
        # At outdoor_temp = 0°C: factor = 2.0 (heating takes twice as long)
        # At outdoor_temp = -10°C: factor = 2.5 (even slower)
        outdoor_factor = 1.0 + (20.0 - outdoor_temp) * 0.05
        outdoor_factor = max(0.5, outdoor_factor)  # Minimum factor of 0.5

        # Effective heating rate considering outdoor conditions
        effective_slope = self.thermal_slope / outdoor_factor

        # Calculate time needed in hours, then convert to minutes
        hours_needed = temp_delta / effective_slope
        minutes_needed = hours_needed * 60.0

        _LOGGER.debug(
            "Preheat calculation: ΔT=%.1f°C, outdoor=%.1f°C, "
            "factor=%.2f, slope=%.2f°C/h, effective_slope=%.2f°C/h, "
            "duration=%.1f min",
            temp_delta,
            outdoor_temp,
            outdoor_factor,
            self.thermal_slope,
            effective_slope,
            minutes_needed,
        )

        return minutes_needed

    def calculate_start_time(
        self,
        current_temp: float,
        target_temp: float,
        outdoor_temp: float,
        target_time: datetime,
    ) -> dict:
        """Calculate when to start heating to reach target temp at target time.
        
        Args:
            current_temp: Current room temperature in Celsius
            target_temp: Target temperature in Celsius
            outdoor_temp: Outdoor temperature in Celsius
            target_time: When the target temperature should be reached
            
        Returns:
            Dictionary with calculation results including:
            - start_time: When to start heating
            - preheat_duration_minutes: How long preheating will take
            - should_start_now: Whether heating should start immediately
        """
        preheat_minutes = self.calculate_preheat_duration(
            current_temp, target_temp, outdoor_temp
        )

        # Calculate when heating should start
        start_time = target_time - timedelta(minutes=preheat_minutes)
        now = datetime.now()

        # Check if we should start now (if start_time is in the past)
        should_start_now = start_time <= now

        result = {
            "start_time": start_time,
            "preheat_duration_minutes": round(preheat_minutes, 1),
            "should_start_now": should_start_now,
            "target_time": target_time,
            "current_temp": current_temp,
            "target_temp": target_temp,
            "outdoor_temp": outdoor_temp,
        }

        _LOGGER.info(
            "Start time calculation: target=%s, start=%s, duration=%.1f min, "
            "start_now=%s",
            target_time.isoformat(),
            start_time.isoformat(),
            preheat_minutes,
            should_start_now,
        )

        return result
