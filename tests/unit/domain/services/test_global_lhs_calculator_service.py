"""Unit tests for GlobalLHSCalculatorService.

Tests the pure domain logic for calculating a single global average LHS
from all heating cycles, regardless of hour or context.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_LEARNED_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.services.global_lhs_calculator_service import (
    GlobalLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestGlobalLHSCalculatorService:
    """Test suite for global LHS calculation."""

    @pytest.fixture
    def service(self) -> GlobalLHSCalculatorService:
        """Create service instance."""
        return GlobalLHSCalculatorService()

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime for testing."""
        return datetime(2025, 2, 9, 0, 0, 0)

    # ===== Helper Methods =====

    def _create_cycle(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
        start_temp: float = 18.0,
        end_temp: float = 20.0,
        target_temp: float = 21.0,
        device_id: str = "climate.test_vtherm",
    ) -> HeatingCycle:
        """Create a test heating cycle.

        Args:
            start_time: Cycle start time
            end_time: Cycle end time (default: 1 hour after start)
            start_temp: Starting temperature
            end_temp: Ending temperature
            target_temp: Target temperature
            device_id: Device identifier

        Returns:
            HeatingCycle object for testing
        """
        if end_time is None:
            end_time = start_time + timedelta(hours=1)

        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None,
        )

    # ===== Test: Empty Cycles List =====

    def test_calculate_global_lhs_empty_cycles_returns_default(
        self, service: GlobalLHSCalculatorService
    ) -> None:
        """Test that empty cycles list returns DEFAULT_LEARNED_SLOPE.

        RED: Should fail because GlobalLHSCalculatorService doesn't exist yet.
        """
        cycles: list[HeatingCycle] = []

        result = service.calculate_global_lhs(cycles)

        assert result == DEFAULT_LEARNED_SLOPE
        assert isinstance(result, float)

    # ===== Test: Single Cycle =====

    def test_calculate_global_lhs_single_cycle_returns_that_lhs(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that single cycle returns its own LHS value.

        RED: Should fail - need to test a single cycle with known LHS.
        Cycle with 1-hour duration, 2°C increase = slope of 2.0°C/h.
        """
        # Cycle: 1 hour, 2°C increase = 2.0°C/h slope
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
            start_temp=18.0,
            end_temp=20.0,
        )

        result = service.calculate_global_lhs([cycle])

        assert result == pytest.approx(2.0, abs=0.01)

    def test_calculate_global_lhs_single_cycle_various_slopes(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test single cycle with different LHS values.

        RED: Test various LHS values to ensure they're preserved.
        """
        test_cases = [
            (18.0, 21.0, 3.0),  # 3°C / 1h = 3.0°C/h
            (18.0, 19.5, 1.5),  # 1.5°C / 1h = 1.5°C/h
            (18.0, 26.0, 8.0),  # 8°C / 1h = 8.0°C/h
        ]

        for start_temp, end_temp, expected_slope in test_cases:
            cycle = self._create_cycle(
                start_time=base_datetime,
                end_time=base_datetime + timedelta(hours=1),
                start_temp=start_temp,
                end_temp=end_temp,
            )

            result = service.calculate_global_lhs([cycle])

            assert result == pytest.approx(expected_slope, abs=0.01)

    # ===== Test: Multiple Cycles =====

    def test_calculate_global_lhs_multiple_cycles_returns_average(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that multiple cycles return their average LHS.

        RED: Test average calculation.
        Cycle 1: 1h, 2°C = 2.0°C/h
        Cycle 2: 1h, 4°C = 4.0°C/h
        Expected: (2.0 + 4.0) / 2 = 3.0°C/h
        """
        cycle1 = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
            start_temp=18.0,
            end_temp=20.0,  # 2°C/h
        )

        cycle2 = self._create_cycle(
            start_time=base_datetime + timedelta(days=1),
            end_time=base_datetime + timedelta(days=1, hours=1),
            start_temp=18.0,
            end_temp=22.0,  # 4°C/h
        )

        result = service.calculate_global_lhs([cycle1, cycle2])

        assert result == pytest.approx(3.0, abs=0.01)

    def test_calculate_global_lhs_three_cycles(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test average with three cycles.

        RED: Test with odd number of cycles.
        Cycle 1: 1.5°C/h
        Cycle 2: 2.5°C/h
        Cycle 3: 3.0°C/h
        Expected: (1.5 + 2.5 + 3.0) / 3 = 2.33°C/h
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime,
                end_time=base_datetime + timedelta(hours=1),
                start_temp=18.0,
                end_temp=19.5,  # 1.5°C/h
            ),
            self._create_cycle(
                start_time=base_datetime + timedelta(days=1),
                end_time=base_datetime + timedelta(days=1, hours=1),
                start_temp=18.0,
                end_temp=20.5,  # 2.5°C/h
            ),
            self._create_cycle(
                start_time=base_datetime + timedelta(days=2),
                end_time=base_datetime + timedelta(days=2, hours=1),
                start_temp=18.0,
                end_temp=21.0,  # 3.0°C/h
            ),
        ]

        result = service.calculate_global_lhs(cycles)

        assert result == pytest.approx(2.333, abs=0.01)

    # ===== Test: Edge Cases =====

    def test_calculate_global_lhs_cycles_with_zero_slope(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test cycles where start_temp == end_temp (zero slope).

        RED: Ensure zero-slope cycles don't break the calculation.
        """
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
            start_temp=20.0,
            end_temp=20.0,  # No heating
        )

        result = service.calculate_global_lhs([cycle])

        assert result == pytest.approx(0.0, abs=0.01)

    def test_calculate_global_lhs_cycles_with_negative_slope(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test cycles where temperature decreases (negative slope).

        RED: Ensure negative slopes are handled gracefully.
        """
        cycle = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=1),
            start_temp=20.0,
            end_temp=18.0,  # Temperature decreased
        )

        result = service.calculate_global_lhs([cycle])

        # Should be negative but calculation should work
        assert result == pytest.approx(-2.0, abs=0.01)

    def test_calculate_global_lhs_mixed_positive_negative_slopes(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test average calculation with mixed positive and negative slopes.

        RED: Test averaging when some cycles have positive, others negative.
        Cycle 1: 2.0°C/h (heating)
        Cycle 2: -1.0°C/h (cooling)
        Expected: (2.0 - 1.0) / 2 = 0.5°C/h
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime,
                end_time=base_datetime + timedelta(hours=1),
                start_temp=18.0,
                end_temp=20.0,  # Positive slope
            ),
            self._create_cycle(
                start_time=base_datetime + timedelta(days=1),
                end_time=base_datetime + timedelta(days=1, hours=1),
                start_temp=20.0,
                end_temp=19.0,  # Negative slope
            ),
        ]

        result = service.calculate_global_lhs(cycles)

        assert result == pytest.approx(0.5, abs=0.01)

    # ===== Test: Variable Duration Cycles =====

    def test_calculate_global_lhs_cycles_with_different_durations(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test cycles with different durations yield correct average slopes.

        RED: Ensure duration is correctly factored into slope calculation.
        Cycle 1: 2 hours, 4°C increase = 2.0°C/h
        Cycle 2: 1 hour, 3°C increase = 3.0°C/h
        Expected: (2.0 + 3.0) / 2 = 2.5°C/h
        """
        cycle1 = self._create_cycle(
            start_time=base_datetime,
            end_time=base_datetime + timedelta(hours=2),
            start_temp=18.0,
            end_temp=22.0,  # 4°C / 2h = 2.0°C/h
        )

        cycle2 = self._create_cycle(
            start_time=base_datetime + timedelta(days=1),
            end_time=base_datetime + timedelta(days=1, hours=1),
            start_temp=18.0,
            end_temp=21.0,  # 3°C / 1h = 3.0°C/h
        )

        result = service.calculate_global_lhs([cycle1, cycle2])

        assert result == pytest.approx(2.5, abs=0.01)

    # ===== Test: Type Validation =====

    def test_calculate_global_lhs_returns_float(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that result is always a float type.

        RED: Ensure type hints are correctly implemented.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime,
                end_time=base_datetime + timedelta(hours=1),
                start_temp=18.0,
                end_temp=20.0,
            )
        ]

        result = service.calculate_global_lhs(cycles)

        assert isinstance(result, float)

    def test_calculate_global_lhs_accepts_list_of_heating_cycles(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that service accepts list[HeatingCycle] parameter.

        RED: Ensure type hints are enforced.
        """
        cycles: list[HeatingCycle] = [
            self._create_cycle(
                start_time=base_datetime,
                end_time=base_datetime + timedelta(hours=1),
                start_temp=18.0,
                end_temp=20.0,
            )
        ]

        # Should not raise type error
        result = service.calculate_global_lhs(cycles)

        assert isinstance(result, float)
        assert result > 0

    # ===== Test: Logging Validation =====

    def test_calculate_global_lhs_logs_debug_on_entry_exit(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime, caplog
    ) -> None:
        """Test that service logs DEBUG level on method entry/exit.

        RED: Verify logging standards are met.
        """
        with caplog.at_level("DEBUG"):
            cycles = [
                self._create_cycle(
                    start_time=base_datetime,
                    end_time=base_datetime + timedelta(hours=1),
                    start_temp=18.0,
                    end_temp=20.0,
                )
            ]
            service.calculate_global_lhs(cycles)

        # Should have DEBUG logs
        debug_logs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(debug_logs) > 0, "No DEBUG logs found"

    def test_calculate_global_lhs_logs_result_at_info_level(
        self, service: GlobalLHSCalculatorService, base_datetime: datetime, caplog
    ) -> None:
        """Test that calculation result is logged at INFO level.

        RED: Verify INFO logs for state changes.
        """
        with caplog.at_level("INFO"):
            cycles = [
                self._create_cycle(
                    start_time=base_datetime,
                    end_time=base_datetime + timedelta(hours=1),
                    start_temp=18.0,
                    end_temp=20.0,
                )
            ]
            service.calculate_global_lhs(cycles)

        # Should have INFO logs about the calculation
        info_logs = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_logs) > 0, "No INFO logs found"
