"""Unit tests for ContextualLHSCalculatorService.

Tests the pure domain logic for grouping cycles by start hour
and calculating contextual heating slopes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestContextualLHSCalculatorService:
    """Test suite for contextual LHS calculation."""

    @pytest.fixture
    def service(self) -> ContextualLHSCalculatorService:
        """Create service instance."""
        return ContextualLHSCalculatorService()

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime for testing."""
        return dt_util.parse_datetime("2025-02-09T00:00:00+00:00")

    # ===== extract_hour_from_cycle Tests =====

    def test_extract_hour_at_midnight(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test extracting hour from cycle at midnight (hour=0)."""
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 0

    def test_extract_hour_at_morning(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test extracting hour from cycle at 06:00."""
        start = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 6

    def test_extract_hour_at_evening(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test extracting hour from cycle at 23:00."""
        start = base_datetime.replace(hour=23)
        cycle = self._create_cycle(
            start_time=start,
            end_time=start + timedelta(minutes=30),
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 23

    # ===== group_cycles_by_start_hour Tests =====

    def test_group_empty_cycles_list(self, service: ContextualLHSCalculatorService) -> None:
        """Test grouping empty cycles list."""
        grouped = service.group_cycles_by_start_hour([])

        assert len(grouped) == 24
        assert all(v == [] for v in grouped.values())

    def test_group_single_cycle_at_hour_6(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test grouping single cycle at hour 6."""
        start = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        grouped = service.group_cycles_by_start_hour([cycle])

        assert len(grouped[6]) == 1
        assert grouped[6][0] == cycle
        for h in range(24):
            if h != 6:
                assert grouped[h] == []

    def test_group_cycles_across_multiple_hours(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test grouping cycles spread across different hours."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=30),
                end_time=base_datetime.replace(hour=7, minute=30),
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=12),
                end_time=base_datetime.replace(hour=13),
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=20),
                end_time=base_datetime.replace(hour=21),
            ),
        ]

        grouped = service.group_cycles_by_start_hour(cycles)

        assert len(grouped[6]) == 2
        assert len(grouped[12]) == 1
        assert len(grouped[20]) == 1
        assert len(grouped[0]) == 0

    # ===== calculate_contextual_lhs_for_hour Tests =====

    def test_calculate_lhs_invalid_hour_negative(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that negative hour raises ValueError."""
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
        )

        with pytest.raises(ValueError, match="target_hour must be 0-23"):
            service.calculate_contextual_lhs_for_hour([cycle], -1)

    def test_calculate_lhs_invalid_hour_too_high(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that hour > 23 raises ValueError."""
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
        )

        with pytest.raises(ValueError, match="target_hour must be 0-23"):
            service.calculate_contextual_lhs_for_hour([cycle], 24)

    def test_calculate_lhs_no_cycles_for_hour(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that no cycles for target hour returns None."""
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=6),
            end_time=base_datetime.replace(hour=7),
        )
        cycles = [cycle]

        result = service.calculate_contextual_lhs_for_hour(cycles, 12)

        assert result is None

    def test_calculate_lhs_empty_cycles_list(self, service: ContextualLHSCalculatorService) -> None:
        """Test that empty cycles list returns None."""
        result = service.calculate_contextual_lhs_for_hour([], 6)

        assert result is None

    def test_calculate_lhs_single_cycle(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculating LHS with single cycle (average of 1 = value itself)."""
        start = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=start,
            end_time=start + timedelta(hours=1),
            start_temp=15.0,
            end_temp=18.0,
        )
        # LHS should be (18-15)/1 = 3.0

        result = service.calculate_contextual_lhs_for_hour([cycle], 6)

        assert result is not None
        assert abs(result - 3.0) < 0.01

    def test_calculate_lhs_two_cycles_average(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculating LHS with two cycles (average = 14.75)."""
        # Cycle 1: start_temp=15, end_temp=18, duration=1h → LHS=3.0
        # But we need to match the test requirement of 15.0 and 14.5
        # Let's create cycles with those exact slopes

        cycle1 = self._create_cycle(
            start_time=base_datetime.replace(hour=6, minute=15),
            end_time=base_datetime.replace(hour=7, minute=15),
            start_temp=15.0,
            end_temp=30.0,  # 15°C rise in 1h = 15.0°C/h
        )
        cycle2 = self._create_cycle(
            start_time=(base_datetime - timedelta(days=1)).replace(hour=6, minute=30),
            end_time=(base_datetime - timedelta(days=1)).replace(hour=7, minute=30),
            start_temp=15.0,
            end_temp=29.5,  # 14.5°C rise in 1h = 14.5°C/h
        )

        result = service.calculate_contextual_lhs_for_hour([cycle1, cycle2], 6)

        assert result is not None
        assert abs(result - 14.75) < 0.01

    def test_calculate_lhs_three_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculating LHS with three cycles."""
        cycles = []
        for day in range(3):
            start = (base_datetime - timedelta(days=day)).replace(hour=6)
            cycle = self._create_cycle(
                start_time=start,
                end_time=start + timedelta(hours=1),
                start_temp=15.0,
                end_temp=15.0 + (10 + day),  # vary the slope
            )
            cycles.append(cycle)

        result = service.calculate_contextual_lhs_for_hour(cycles, 6)

        # Slopes: 10, 11, 12 → average = 11.0
        assert result is not None
        assert abs(result - 11.0) < 0.01

    # ===== calculate_all_contextual_lhs Tests =====

    def test_calculate_all_contextual_lhs_empty_cycles(
        self, service: ContextualLHSCalculatorService
    ) -> None:
        """Test calculating all contextual LHS with no cycles."""
        result = service.calculate_all_contextual_lhs([])

        assert len(result) == 24
        assert all(v is None for v in result.values())

    def test_calculate_all_contextual_lhs_single_cycle_at_hour_6(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test all hours calculated with cycles only at hour 6."""
        start = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=start,
            end_time=start + timedelta(hours=1),
            start_temp=15.0,
            end_temp=18.0,
        )

        result = service.calculate_all_contextual_lhs([cycle])

        assert len(result) == 24
        assert result[6] is not None
        for h in range(24):
            if h != 6:
                assert result[h] is None

    def test_calculate_all_contextual_lhs_cycles_across_hours(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test all hours with cycles distributed."""
        cycles = []
        for hour in [0, 6, 12, 18]:
            start = base_datetime.replace(hour=hour)
            cycle = self._create_cycle(
                start_time=start,
                end_time=start + timedelta(hours=1),
            )
            cycles.append(cycle)

        result = service.calculate_all_contextual_lhs(cycles)

        assert len(result) == 24
        assert result[0] is not None
        assert result[6] is not None
        assert result[12] is not None
        assert result[18] is not None
        for h in [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23]:
            assert result[h] is None

    # ===== Helper Methods =====

    def _create_cycle(
        self,
        start_time: datetime,
        end_time: datetime,
        start_temp: float = 15.0,
        end_temp: float = 18.0,
        target_temp: float = 20.0,
        dead_time_cycle_minutes: float = 0,
    ) -> HeatingCycle:
        """Helper to create a test HeatingCycle."""
        return HeatingCycle(
            device_id="test_device",
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            dead_time_cycle_minutes=dead_time_cycle_minutes,
            tariff_details=None,
        )
