"""Tests for LHS calculator services."""

import unittest
from datetime import datetime, timedelta, timezone

from custom_components.intelligent_heating_pilot.domain.constants import DEFAULT_LEARNED_SLOPE
from custom_components.intelligent_heating_pilot.domain.services import (
    ContextualLHSCalculatorService,
    GlobalLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import HeatingCycle


class TestGlobalLHSCalculatorService(unittest.TestCase):
    """Tests for global LHS calculator service."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = GlobalLHSCalculatorService()

    def _create_cycle(
        self,
        start_time: datetime,
        duration_hours: float,
        temp_increase: float,
        device_id: str = "test_device",
    ) -> HeatingCycle:
        """Helper to create a heating cycle with specific slope."""
        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = start_temp + temp_increase
        target_temp = end_temp + 0.5  # Slightly above end temp

        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None,
        )

    def test_calculate_global_lhs_empty_list(self):
        """Test calculating global LHS with empty list."""
        result = self.service.calculate_global_lhs([])

        # Should return default
        self.assertEqual(result, DEFAULT_LEARNED_SLOPE)

    def test_calculate_global_lhs_single_cycle(self):
        """Test calculating global LHS with a single cycle."""
        # Create a cycle with 2°C increase in 1 hour = 2°C/h slope
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        cycle = self._create_cycle(start_time=base_time, duration_hours=1.0, temp_increase=2.0)

        result = self.service.calculate_global_lhs([cycle])

        # Should return the cycle's slope
        self.assertAlmostEqual(result, 2.0, places=2)

    def test_calculate_global_lhs_multiple_cycles(self):
        """Test calculating global LHS with multiple cycles."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)

        # Create cycles with different slopes: 2.0, 2.2, 2.4 °C/h
        cycles = [
            self._create_cycle(base_time, duration_hours=1.0, temp_increase=2.0),
            self._create_cycle(
                base_time + timedelta(hours=2), duration_hours=1.0, temp_increase=2.2
            ),
            self._create_cycle(
                base_time + timedelta(hours=4), duration_hours=1.0, temp_increase=2.4
            ),
        ]

        result = self.service.calculate_global_lhs(cycles)

        # Average should be (2.0 + 2.2 + 2.4) / 3 = 2.2
        self.assertAlmostEqual(result, 2.2, places=2)

    def test_calculate_global_lhs_with_varying_durations(self):
        """Test that global LHS handles cycles of different durations correctly."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)

        # Different durations but similar heating rates
        cycles = [
            self._create_cycle(base_time, duration_hours=0.5, temp_increase=1.0),  # 2.0°C/h
            self._create_cycle(
                base_time + timedelta(hours=1), duration_hours=2.0, temp_increase=4.0
            ),  # 2.0°C/h
            self._create_cycle(
                base_time + timedelta(hours=4), duration_hours=1.0, temp_increase=2.0
            ),  # 2.0°C/h
        ]

        result = self.service.calculate_global_lhs(cycles)

        # All have 2.0°C/h slope, average should be 2.0
        self.assertAlmostEqual(result, 2.0, places=2)


class TestContextualLHSCalculatorService(unittest.TestCase):
    """Tests for contextual LHS calculator service."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ContextualLHSCalculatorService()

    def _create_cycle(
        self,
        start_time: datetime,
        duration_hours: float,
        temp_increase: float,
        device_id: str = "test_device",
    ) -> HeatingCycle:
        """Helper to create a heating cycle with specific slope."""
        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = start_temp + temp_increase
        target_temp = end_temp + 0.5

        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None,
        )

    def test_calculate_contextual_lhs_invalid_hour(self):
        """Test calculating contextual LHS with invalid hour."""
        with self.assertRaises(ValueError):
            self.service.calculate_contextual_lhs_for_hour([], target_hour=24)

        with self.assertRaises(ValueError):
            self.service.calculate_contextual_lhs_for_hour([], target_hour=-1)

    def test_calculate_contextual_lhs_no_cycles(self):
        """Test contextual LHS returns None when no cycles match."""
        result = self.service.calculate_contextual_lhs_for_hour([], target_hour=15)

        self.assertIsNone(result)

    def test_calculate_contextual_lhs_filters_by_start_hour(self):
        """Test contextual LHS filters cycles by start hour."""
        base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)

        cycles = [
            self._create_cycle(base_time, duration_hours=1.0, temp_increase=1.0),
            self._create_cycle(
                base_time + timedelta(hours=1), duration_hours=1.0, temp_increase=2.0
            ),
            self._create_cycle(
                base_time + timedelta(hours=1), duration_hours=1.0, temp_increase=4.0
            ),
        ]

        result = self.service.calculate_contextual_lhs_for_hour(cycles, target_hour=15)

        # Slopes at hour 15: 2.0 and 4.0 -> average 3.0
        self.assertAlmostEqual(result, 3.0, places=2)  # type: ignore

    def test_group_cycles_by_start_hour(self):
        """Test grouping cycles by start hour."""
        base_time = datetime(2025, 12, 18, 8, 0, 0, tzinfo=timezone.utc)

        cycles = [
            self._create_cycle(base_time, duration_hours=1.0, temp_increase=1.0),
            self._create_cycle(
                base_time + timedelta(hours=2), duration_hours=1.0, temp_increase=1.0
            ),
            self._create_cycle(
                base_time + timedelta(hours=2), duration_hours=1.0, temp_increase=2.0
            ),
        ]

        grouped = self.service.group_cycles_by_start_hour(cycles)

        self.assertEqual(len(grouped[8]), 1)
        self.assertEqual(len(grouped[10]), 2)

    def test_calculate_all_contextual_lhs(self):
        """Test calculating contextual LHS for all 24 hours."""
        base_time = datetime(2025, 12, 18, 6, 0, 0, tzinfo=timezone.utc)
        cycles = [
            self._create_cycle(base_time, duration_hours=1.0, temp_increase=2.0),
            self._create_cycle(
                base_time + timedelta(hours=3), duration_hours=1.0, temp_increase=3.0
            ),
        ]

        result = self.service.calculate_all_contextual_lhs(cycles)

        self.assertEqual(len(result), 24)
        self.assertAlmostEqual(result[6], 2.0, places=2)  # type: ignore
        self.assertAlmostEqual(result[9], 3.0, places=2)  # type: ignore
        self.assertIsNone(result[0])


if __name__ == "__main__":
    unittest.main()
