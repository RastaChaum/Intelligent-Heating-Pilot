"""LHS (Learning Heating Slope) calculation service.

This service contains the domain logic for calculating heating slopes
from heating cycles using simple averaging methods.
"""
from __future__ import annotations

import logging
from datetime import time

from ..value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)

DEFAULT_HEATING_SLOPE = 2.0  # °C/h - Conservative default


class LHSCalculationService:
    """Service for calculating Learning Heating Slope from heating cycles.
    
    This service provides domain logic for:
    - Calculating global LHS from all heating cycles
    - Calculating contextual LHS for cycles active at a specific hour
    - Handling edge cases (insufficient data, empty lists)
    - Providing sensible defaults
    
    All calculations are pure domain logic with no infrastructure dependencies.
    """
    
    def calculate_simple_average(self, slope_values: list[float]) -> float:
        """Calculate simple average from raw slope values.
        
        This method is provided for backward compatibility with legacy code
        that still uses raw slope values instead of HeatingCycle objects.
        
        Args:
            slope_values: List of slope values in °C/hour
            
        Returns:
            Simple average in °C/hour, or default if no data
        """
        _LOGGER.debug("Calculating simple average from %d slope values", len(slope_values))
        
        if not slope_values:
            _LOGGER.debug(
                "No slope values provided, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        avg_slope = sum(slope_values) / len(slope_values)
        
        _LOGGER.debug(
            "Calculated simple average from %d values: %.2f°C/h",
            len(slope_values),
            avg_slope
        )
        
        return avg_slope
    
    def calculate_global_lhs(self, heating_cycles: list[HeatingCycle]) -> float:
        """Calculate global LHS as simple average of all heating cycle slopes.
        
        Args:
            heating_cycles: List of heating cycles to analyze
            
        Returns:
            Average heating slope in °C/hour, or default if no data
        """
        _LOGGER.info("Calculating global LHS from %d heating cycles", len(heating_cycles))
        
        if not heating_cycles:
            _LOGGER.debug(
                "No heating cycles provided, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Calculate simple average
        total_slope = sum(cycle.avg_heating_slope for cycle in heating_cycles)
        avg_slope = total_slope / len(heating_cycles)
        
        _LOGGER.info(
            "Calculated global LHS from %d cycles: %.2f°C/h",
            len(heating_cycles),
            avg_slope
        )
        
        return avg_slope
    
    def calculate_contextual_lhs(
        self,
        heating_cycles: list[HeatingCycle],
        target_hour: int
    ) -> float:
        """Calculate contextual LHS for cycles active at a specific hour.
        
        A cycle is considered "active at target_hour" if it started before or at
        target_hour and ended after target_hour. This captures cycles that were
        heating during the specified hour.
        
        Args:
            heating_cycles: List of all heating cycles to filter
            target_hour: Hour of day (0-23) to filter cycles by
            
        Returns:
            Average heating slope for cycles active at target_hour, or default if no data
        """
        _LOGGER.info(
            "Calculating contextual LHS for hour %d from %d heating cycles",
            target_hour,
            len(heating_cycles)
        )
        
        if not 0 <= target_hour <= 23:
            raise ValueError(f"target_hour must be 0-23, got {target_hour}")
        
        if not heating_cycles:
            _LOGGER.debug(
                "No heating cycles provided, using default: %.2f°C/h",
                DEFAULT_HEATING_SLOPE
            )
            return DEFAULT_HEATING_SLOPE
        
        # Filter cycles active at target hour
        def is_active_at_hour(cycle: HeatingCycle) -> bool:
            """Check if cycle was active during target hour."""
            # Create time objects for comparison (date-agnostic)
            start_time = cycle.start_time.time()
            end_time = cycle.end_time.time()
            target_time = time(hour=target_hour, minute=0, second=0)
            
            # Handle same-day cycles
            if cycle.start_time.date() == cycle.end_time.date():
                return start_time <= target_time < end_time
            
            # Handle multi-day cycles (crosses midnight)
            # Cycle is active if target_hour is after start OR before end
            return target_time >= start_time or target_time < end_time
        
        active_cycles = [c for c in heating_cycles if is_active_at_hour(c)]
        
        if not active_cycles:
            lhs = self.calculate_global_lhs(heating_cycles)
            _LOGGER.debug(
                "No cycles active at hour %d, using global: %.2f°C/h",
                target_hour,
                lhs
            )
            return lhs
        
        # Calculate simple average
        total_slope = sum(cycle.avg_heating_slope for cycle in active_cycles)
        avg_slope = total_slope / len(active_cycles)
        
        if avg_slope <= 0:
            lhs = self.calculate_global_lhs(heating_cycles)
            _LOGGER.debug(
                "Calculated invalid average slope %.2f°C/h for hour %d, using default: %.2f°C/h",
                avg_slope,
                target_hour,
                lhs
            )
            return lhs

        _LOGGER.info(
            "Calculated contextual LHS for hour %d from %d active cycles: %.2f°C/h",
            target_hour,
            len(active_cycles),
            avg_slope
        )
        
        return avg_slope
