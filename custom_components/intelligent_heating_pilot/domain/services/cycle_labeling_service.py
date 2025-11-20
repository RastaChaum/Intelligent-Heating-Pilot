"""Cycle labeling service for calculating optimal heating durations."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)


class CycleLabelingService:
    """Service for calculating optimal heating durations using error-driven labeling.
    
    This service implements the error-driven labeling methodology:
    - Observes when target temperature was actually reached
    - Calculates the error (late/early) relative to target time
    - Computes optimal duration that would have eliminated the error
    """
    
    def calculate_optimal_duration(
        self,
        actual_duration_minutes: float,
        error_minutes: float,
    ) -> float:
        """Calculate optimal duration based on observed error.
        
        Formula: optimal_duration = actual_duration - error
        
        If heating finished early (negative error): optimal should be longer
        If heating finished late (positive error): optimal should be shorter
        
        Args:
            actual_duration_minutes: How long heating actually took
            error_minutes: Difference between target_reached_at and target_time
                          (positive = late, negative = early)
        
        Returns:
            Optimal duration in minutes that would have reached target on time.
        """
        optimal = actual_duration_minutes - error_minutes
        
        # Ensure positive duration (minimum 5 minutes)
        optimal = max(5.0, optimal)
        
        _LOGGER.debug(
            "Calculated optimal duration: %.1f min (actual: %.1f min, error: %.1f min)",
            optimal,
            actual_duration_minutes,
            error_minutes,
        )
        
        return optimal
    
    def calculate_error_minutes(
        self,
        target_reached_at: datetime,
        target_time: datetime,
    ) -> float:
        """Calculate error in minutes between actual and target times.
        
        Args:
            target_reached_at: When target temperature was actually reached
            target_time: When target temperature should have been reached
            
        Returns:
            Error in minutes (positive = late, negative = early).
        """
        delta = target_reached_at - target_time
        error_minutes = delta.total_seconds() / 60.0
        
        return error_minutes
    
    def label_heating_cycle(
        self,
        cycle: HeatingCycle,
    ) -> float:
        """Calculate the target label (Y) for a heating cycle.
        
        This is the main labeling function that takes a reconstructed
        heating cycle and calculates the optimal duration label.
        
        Args:
            cycle: Heating cycle with observed data
            
        Returns:
            Optimal duration in minutes (the Y label for ML training).
            
        Raises:
            ValueError: If cycle data is invalid or incomplete.
        """
        if cycle.target_reached_at is None:
            raise ValueError(
                f"Cannot label cycle {cycle.cycle_id}: target never reached"
            )
        
        # Calculate error
        error = self.calculate_error_minutes(
            cycle.target_reached_at,
            cycle.target_time,
        )
        
        # Calculate optimal duration
        optimal = self.calculate_optimal_duration(
            cycle.actual_duration_minutes,
            error,
        )
        
        _LOGGER.debug(
            "Labeled cycle %s: optimal=%.1f min (actual=%.1f min, error=%.1f min)",
            cycle.cycle_id,
            optimal,
            cycle.actual_duration_minutes,
            error,
        )
        
        return optimal
    
    def is_cycle_valid_for_training(
        self,
        cycle: HeatingCycle,
        max_error_minutes: float = 30.0,
    ) -> bool:
        """Check if a heating cycle is valid for training.
        
        Filters out cycles with:
        - Missing target_reached_at (target never reached)
        - Excessive error (system malfunction or unusual conditions)
        - Negative or zero actual duration
        
        Args:
            cycle: Heating cycle to validate
            max_error_minutes: Maximum acceptable error in minutes
            
        Returns:
            True if cycle is valid for training, False otherwise.
        """
        # Must have reached target
        if cycle.target_reached_at is None:
            _LOGGER.debug(
                "Cycle %s invalid: target never reached",
                cycle.cycle_id,
            )
            return False
        
        # Must have positive duration
        if cycle.actual_duration_minutes <= 0:
            _LOGGER.debug(
                "Cycle %s invalid: non-positive duration (%.1f min)",
                cycle.cycle_id,
                cycle.actual_duration_minutes,
            )
            return False
        
        # Check error magnitude
        error = abs(cycle.error_minutes)
        if error > max_error_minutes:
            _LOGGER.debug(
                "Cycle %s invalid: excessive error (%.1f min > %.1f min threshold)",
                cycle.cycle_id,
                error,
                max_error_minutes,
            )
            return False
        
        return True
