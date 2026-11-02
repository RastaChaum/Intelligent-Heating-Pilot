"""Service for calculating global Learning Heating Slope (LHS).

Pure domain logic for calculating average heating slope from all cycles,
regardless of time of day. No Home Assistant dependencies.
"""

from __future__ import annotations

import logging

from ..constants import DEFAULT_LEARNED_SLOPE
from ..value_objects import HeatingCycle
from .learning_cycle_filter import filter_learnable_cycles

_LOGGER = logging.getLogger(__name__)


class GlobalLHSCalculatorService:
    """Calculate global LHS from all heating cycles.

    Responsibilities:
    - Calculate average heating slope from all learnable cycles
    - Return default slope when no learnable cycle is available
    - Handle edge cases gracefully

    Pure domain logic with no Home Assistant dependencies.
    """

    def calculate_global_lhs(self, cycles: list[HeatingCycle]) -> float:
        """Calculate average LHS from all heating cycles.

        Args:
            cycles: List of all heating cycles to analyze

        Returns:
            float: Average heating slope in °C/hour, or DEFAULT_LEARNED_SLOPE if no
            learnable cycle remains

        Calculation:
            Cycles the shared learning rule rejects (disturbed, never warmed the room,
            no heating) are left out, as for the contextual LHS, then the remaining
            slopes are averaged, however slow.
        """
        _LOGGER.debug("Calculating global LHS from %d cycles", len(cycles))

        if not cycles:
            _LOGGER.info(
                "No cycles available for global LHS calculation, returning default slope: %.2f°C/h",
                DEFAULT_LEARNED_SLOPE,
            )
            return DEFAULT_LEARNED_SLOPE

        # Same rule as the contextual LHS and the dead time (#223, #255)
        lhs_values = [cycle.avg_heating_slope for cycle in filter_learnable_cycles(cycles)]

        if not lhs_values:
            _LOGGER.info(
                "No learnable cycle, returning default: %.2f°C/h",
                DEFAULT_LEARNED_SLOPE,
            )
            return DEFAULT_LEARNED_SLOPE

        global_lhs = sum(lhs_values) / len(lhs_values)

        _LOGGER.info(
            "Calculated global LHS: %.2f°C/h from %d learnable cycles out of %d",
            global_lhs,
            len(lhs_values),
            len(cycles),
        )
        _LOGGER.debug("Global LHS calculation complete")

        return global_lhs
