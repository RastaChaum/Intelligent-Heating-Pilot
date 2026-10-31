"""Service for calculating average dead time from heating cycles.

Pure domain logic for aggregating dead_time_cycle_minutes values
from HeatingCycle instances. No Home Assistant dependencies.
"""

from __future__ import annotations

import logging

from ..value_objects import HeatingCycle
from .learning_cycle_filter import filter_realistic_cycles

_LOGGER = logging.getLogger(__name__)


class DeadTimeCalculationService:
    """Calculate average dead time from heating cycles.

    Responsibilities:
    - Keep the cycles realistic enough for the LHS that have a valid dead_time_cycle_minutes
    - Compute average dead time across valid cycles
    - Return None when no valid data exists

    Pure domain logic with no Home Assistant dependencies.
    """

    def calculate_average_dead_time(self, heating_cycles: list[HeatingCycle]) -> float | None:
        """Calculate average dead_time from cycles with valid dead_time_cycle_minutes.

        Only cycles kept for the LHS by the shared realistic-cycle rule are averaged. A
        cycle rejected there, typically one whose temperature fell and only climbed back
        to the threshold at its last reading, has a dead time as long as the cycle and
        would add its whole duration to the learned dead time (#245).

        Args:
            heating_cycles: List of heating cycles to analyze

        Returns:
            Average dead time in minutes, or None if no valid data
        """
        _LOGGER.debug(
            "Entering calculate_average_dead_time: cycles=%d",
            len(heating_cycles),
        )

        realistic_cycles = filter_realistic_cycles(heating_cycles)
        cycles_with_dead_time = [cycle for cycle in realistic_cycles if cycle.has_dead_time]
        _LOGGER.debug(
            "Dead time candidates: %d realistic cycles of %d, %d with a dead time",
            len(realistic_cycles),
            len(heating_cycles),
            len(cycles_with_dead_time),
        )

        if not cycles_with_dead_time:
            _LOGGER.debug("No cycles with valid dead_time_cycle_minutes")
            _LOGGER.debug("Exiting calculate_average_dead_time: result=None")
            return None

        total_dead_time = sum(
            cycle.dead_time_cycle_minutes
            for cycle in cycles_with_dead_time
            if cycle.dead_time_cycle_minutes is not None
        )
        avg_dead_time = total_dead_time / len(cycles_with_dead_time)

        _LOGGER.debug(
            "Calculated average dead_time from %d cycles: %.1f minutes",
            len(cycles_with_dead_time),
            avg_dead_time,
        )
        _LOGGER.debug("Exiting calculate_average_dead_time: result=%.1f", avg_dead_time)

        return avg_dead_time
