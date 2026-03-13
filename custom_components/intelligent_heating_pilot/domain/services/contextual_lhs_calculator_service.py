"""Service for calculating contextual Learning Heating Slope (LHS).

Pure domain logic for grouping cycles by start hour and calculating
average heating slopes per hour. No Home Assistant dependencies.
"""

from __future__ import annotations

import logging

from ..value_objects import HeatingCycle

_LOGGER = logging.getLogger(__name__)


class ContextualLHSCalculatorService:
    """Calculate contextual LHS grouped by start hour.

    Responsibilities:
    - Extract hour from cycle start_time
    - Group cycles by start hour
    - Calculate average LHS per hour
    - Handle empty groups gracefully

    Pure domain logic with no Home Assistant dependencies.
    """

    def extract_hour_from_cycle(self, cycle: HeatingCycle) -> int:
        """Extract hour (0-23) from cycle start time.

        Args:
            cycle: The heating cycle

        Returns:
            Hour of day (0-23)
        """
        _LOGGER.debug("Extracting hour from cycle started at %s", cycle.start_time)
        hour = cycle.start_time.hour
        _LOGGER.debug("Extracted hour: %d", hour)
        return hour

    def group_cycles_by_start_hour(
        self, cycles: list[HeatingCycle]
    ) -> dict[int, list[HeatingCycle]]:
        """Group cycles by their start_time hour.

        Args:
            cycles: All extracted heating cycles

        Returns:
            Mapping {hour: [cycles_starting_at_hour]}
        """
        _LOGGER.debug("Grouping %d cycles by start hour", len(cycles))

        grouped: dict[int, list[HeatingCycle]] = {h: [] for h in range(24)}

        for cycle in cycles:
            hour = self.extract_hour_from_cycle(cycle)
            grouped[hour].append(cycle)

        # Log summary
        non_empty = {h: len(c) for h, c in grouped.items() if c}
        _LOGGER.info("Grouped cycles by hour: %s", non_empty)

        return grouped

    def calculate_contextual_lhs_for_hour(
        self, cycles: list[HeatingCycle], target_hour: int
    ) -> float | None:
        """Calculate average LHS for cycles starting at target_hour.

        Args:
            cycles: All extracted cycles
            target_hour: Hour (0-23) to filter by

        Returns:
            Average LHS value or None if no data for this hour

        Raises:
            ValueError: If target_hour not in 0-23
        """
        if not 0 <= target_hour <= 23:
            raise ValueError(f"target_hour must be 0-23, got {target_hour}")

        _LOGGER.debug(
            "Calculating contextual LHS for hour %d from %d cycles", target_hour, len(cycles)
        )

        # Filter cycles starting at target hour
        matching_cycles = [c for c in cycles if self.extract_hour_from_cycle(c) == target_hour]

        if not matching_cycles:
            _LOGGER.debug("No cycles found for hour %d", target_hour)
            return None

        # Filter out non-positive slopes: cycles where temperature didn't rise
        # carry no useful learning data about heating speed
        lhs_values = [c.avg_heating_slope for c in matching_cycles if c.avg_heating_slope > 0]

        if not lhs_values:
            _LOGGER.debug("No cycles with positive heating slope for hour %d", target_hour)
            return None

        avg_lhs = sum(lhs_values) / len(lhs_values)

        _LOGGER.info(
            "Calculated contextual LHS for hour %d: %.2f°C/h from %d cycles",
            target_hour,
            avg_lhs,
            len(matching_cycles),
        )

        return avg_lhs

    def calculate_all_contextual_lhs(self, cycles: list[HeatingCycle]) -> dict[int, float | None]:
        """Calculate contextual LHS for all 24 hours.

        Args:
            cycles: All extracted cycles

        Returns:
            Mapping {hour: avg_lhs_value_or_none}
        """
        _LOGGER.info("Calculating contextual LHS for all 24 hours")

        result = {}
        for hour in range(24):
            lhs = self.calculate_contextual_lhs_for_hour(cycles, hour)
            result[hour] = lhs

        hours_with_data = sum(1 for v in result.values() if v is not None)
        _LOGGER.info("Contextual LHS calculated for %d hours with data", hours_with_data)

        return result
