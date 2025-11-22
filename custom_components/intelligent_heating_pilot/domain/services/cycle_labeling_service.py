"""Cycle labeling service for calculating heating durations."""
from __future__ import annotations

import logging

from ..value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)


class CycleLabelingService:
    """Service for calculating heating duration labels from observed cycles.
    
    With the simplified cycle detection approach, cycles are detected based on
    actual heating behavior (heat mode + temperature delta >= 0.3°C).
    The label is simply the actual duration it took to heat the room.
    """
    
    def label_heating_cycle(
        self,
        cycle: HeatingCycle,
    ) -> float:
        """Calculate the target label (Y) for a heating cycle.
        
        The label is the actual duration of the heating cycle, which represents
        the time it took to heat from initial_temp toward target_temp under
        the observed environmental conditions.
        
        Args:
            cycle: Heating cycle with observed data
            
        Returns:
            Duration in minutes (the Y label for ML training).
        """
        duration = cycle.duration_minutes
        
        _LOGGER.debug(
            "Labeled cycle %s: duration=%.1f min (%.1f→%.1f°C)",
            cycle.cycle_id,
            duration,
            cycle.initial_temp,
            cycle.final_temp,
        )
        
        return duration
    
    def is_cycle_valid_for_training(
        self,
        cycle: HeatingCycle,
        min_duration_minutes: float = 5.0,
        max_duration_minutes: float = 360.0,
        min_temp_increase: float = 0.1,
    ) -> bool:
        """Check if a heating cycle is valid for training.
        
        Filters out cycles with:
        - Very short duration (likely noise or false positives)
        - Extremely long duration (system malfunction or unusual conditions)
        - No meaningful temperature increase
        
        Args:
            cycle: Heating cycle to validate
            min_duration_minutes: Minimum acceptable duration
            max_duration_minutes: Maximum acceptable duration
            min_temp_increase: Minimum temperature increase required (°C)
            
        Returns:
            True if cycle is valid for training, False otherwise.
        """
        # Must have positive duration within reasonable bounds
        if cycle.duration_minutes < min_duration_minutes:
            _LOGGER.debug(
                "Cycle %s invalid: too short (%.1f min < %.1f min)",
                cycle.cycle_id,
                cycle.duration_minutes,
                min_duration_minutes,
            )
            return False
        
        if cycle.duration_minutes > max_duration_minutes:
            _LOGGER.debug(
                "Cycle %s invalid: too long (%.1f min > %.1f min)",
                cycle.cycle_id,
                cycle.duration_minutes,
                max_duration_minutes,
            )
            return False
        
        # Must show some temperature increase
        temp_increase = cycle.final_temp - cycle.initial_temp
        if temp_increase < min_temp_increase:
            _LOGGER.debug(
                "Cycle %s invalid: insufficient temperature increase (%.2f°C < %.2f°C)",
                cycle.cycle_id,
                temp_increase,
                min_temp_increase,
            )
            return False
        
        return True
