"""Additional comprehensive tests for ContextualLHSCalculatorService.

Adds supplementary test scenarios beyond basic functionality,
focusing on data validation, regression prevention, and performance.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestContextualLHSCalculatorServiceAdvanced:
    """Advanced test suite for contextual LHS calculation scenarios."""

    @pytest.fixture
    def service(self) -> ContextualLHSCalculatorService:
        """Create service instance."""
        return ContextualLHSCalculatorService()

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
        """Create a test heating cycle."""
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

    # ===== Test: Cycle Grouping Accuracy =====

    def test_cycles_grouped_only_by_start_hour_not_end_hour(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that grouping uses start_time.hour, not end_time.hour.

        RED: Cycle starting at 23:50, ending at 00:30 next day.
        Should be in hour 23, not hour 0.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=23, minute=50),
            end_time=base_datetime.replace(day=10, hour=0, minute=30),
            start_temp=18.0,
            end_temp=20.0,
        )

        grouped = service.group_cycles_by_start_hour([cycle])

        # Must be in hour 23
        assert len(grouped[23]) == 1
        assert len(grouped[0]) == 0

    def test_all_hours_initialized_in_grouped_result(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that grouped result has all 24 hours, even if empty.

        RED: Result dict must always have keys 0-23.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=6),
            start_temp=18.0,
            end_temp=20.0,
        )

        grouped = service.group_cycles_by_start_hour([cycle])

        # Must have exactly 24 keys: 0-23
        assert len(grouped) == 24
        assert list(grouped.keys()) == list(range(24))

        # Hour 6 should have the cycle
        assert len(grouped[6]) == 1

        # All other hours should be empty lists
        for hour in range(24):
            if hour != 6:
                assert grouped[hour] == []

    def test_multiple_cycles_same_hour_all_included(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that all cycles for the same hour are included.

        RED: Should group 5 cycles all at hour 6 correctly.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=i * 10),
                start_temp=18.0,
                end_temp=20.0,
            )
            for i in range(5)
        ]

        grouped = service.group_cycles_by_start_hour(cycles)

        assert len(grouped[6]) == 5

    # ===== Test: Contextual LHS Calculation for Specific Hour =====

    def test_calculate_for_hour_with_single_cycle(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculate_contextual_lhs_for_hour with single cycle.

        RED: Should return that cycle's LHS.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=6),
            end_time=base_datetime.replace(hour=7),
            start_temp=18.0,
            end_temp=20.0,
        )

        result = service.calculate_contextual_lhs_for_hour([cycle], 6)

        assert result is not None
        assert result == pytest.approx(2.0, abs=0.01)

    def test_calculate_for_hour_with_multiple_cycles_returns_average(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that multiple cycles for same hour return their average.

        RED: Two cycles at hour 6 with slopes 2.0 and 4.0 → avg 3.0.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                end_time=base_datetime.replace(hour=7, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2.0°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(day=7, hour=6, minute=0),
                end_time=base_datetime.replace(day=7, hour=7, minute=0),
                start_temp=18.0,
                end_temp=22.0,  # 4.0°C/h
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 6)

        assert result is not None
        assert result == pytest.approx(3.0, abs=0.01)

    def test_calculate_for_hour_returns_none_when_no_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that hour with no cycles returns None.

        RED: Query for hour 12 when all cycles are at hour 6.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                start_temp=18.0,
                end_temp=20.0,
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 12)

        assert result is None

    def test_calculate_for_hour_ignores_cycles_from_other_hours(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that only cycles from target hour are included.

        RED: Cycles from hour 6 should not be included when calculating hour 7.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2.0°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=7, minute=0),
                start_temp=18.0,
                end_temp=25.0,  # 7.0°C/h
            ),
        ]

        result_6 = service.calculate_contextual_lhs_for_hour(cycles, 6)
        result_7 = service.calculate_contextual_lhs_for_hour(cycles, 7)

        assert result_6 == pytest.approx(2.0, abs=0.01)
        assert result_7 == pytest.approx(7.0, abs=0.01)
        assert result_6 != result_7

    # ===== Test: Target Hour Validation =====

    def test_calculate_for_hour_rejects_negative_hour(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that target_hour must be >= 0.

        RED: Should raise ValueError for hour < 0.
        """
        cycles = [self._create_cycle(base_datetime)]

        with pytest.raises(ValueError, match="target_hour must be 0-23"):
            service.calculate_contextual_lhs_for_hour(cycles, -1)

    def test_calculate_for_hour_rejects_hour_above_23(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that target_hour must be <= 23.

        RED: Should raise ValueError for hour > 23.
        """
        cycles = [self._create_cycle(base_datetime)]

        with pytest.raises(ValueError, match="target_hour must be 0-23"):
            service.calculate_contextual_lhs_for_hour(cycles, 24)

    def test_calculate_for_hour_accepts_boundary_0(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that hour=0 (midnight) is valid.

        RED: Edge case for boundary.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=0),
            start_temp=18.0,
            end_temp=20.0,
        )

        result = service.calculate_contextual_lhs_for_hour([cycle], 0)

        assert result is not None

    def test_calculate_for_hour_accepts_boundary_23(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that hour=23 (11 PM) is valid.

        RED: Edge case for boundary.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=23),
            start_temp=18.0,
            end_temp=20.0,
        )

        result = service.calculate_contextual_lhs_for_hour([cycle], 23)

        assert result is not None

    # ===== Test: calculate_all_contextual_lhs Returns Correct Structure =====

    def test_calculate_all_returns_dict_with_24_entries(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that calculate_all always returns dict[int, float | None] with 24 keys.

        RED: Must return exactly 24 entries.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                start_temp=18.0,
                end_temp=20.0,
            ),
        ]

        result = service.calculate_all_contextual_lhs(cycles)

        assert isinstance(result, dict)
        assert len(result) == 24
        assert set(result.keys()) == set(range(24))

    def test_calculate_all_values_are_float_or_none(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that all values in result are float or None.

        RED: Type validation.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                start_temp=18.0,
                end_temp=20.0,
            ),
        ]

        result = service.calculate_all_contextual_lhs(cycles)

        for _, value in result.items():
            assert isinstance(value, (float, type(None)))

    def test_calculate_all_hours_with_data_logged(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime, caplog
    ) -> None:
        """Test that service logs INFO about hours with data.

        RED: Verify logging standards (INFO for state changes).
        """
        with caplog.at_level("INFO"):
            cycles = [
                self._create_cycle(
                    start_time=base_datetime.replace(hour=6),
                    start_temp=18.0,
                    end_temp=20.0,
                ),
                self._create_cycle(
                    start_time=base_datetime.replace(hour=12),
                    start_temp=18.0,
                    end_temp=20.0,
                ),
            ]
            service.calculate_all_contextual_lhs(cycles)

        info_logs = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_logs) > 0

    # ===== Test: Performance =====

    def test_calculate_all_completes_in_reasonable_time(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that calculation completes quickly (<1ms for 100 cycles).

        RED: Performance benchmark.
        """
        import time

        # Create 100 cycles distributed across hours
        cycles = [
            self._create_cycle(
                start_time=base_datetime + timedelta(hours=i),
                start_temp=18.0,
                end_temp=20.0,
            )
            for i in range(100)
        ]

        start = time.time()
        service.calculate_all_contextual_lhs(cycles)
        elapsed = time.time() - start

        # Should complete in < 100ms (generous for pytest)
        assert elapsed < 0.1, f"Calculation took {elapsed:.3f}s, expected < 0.1s"

    # ===== Test: Edge Cases with Zero/Negative Slopes =====

    def test_contextual_lhs_excludes_cycles_with_zero_slope(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that cycles with zero slope are excluded from average.

        Zero slope means no actual heating occurred — not useful for learning.
        Only positive-slope cycles contribute to the average.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                end_time=base_datetime.replace(hour=7, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2.0°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(day=7, hour=6, minute=0),
                end_time=base_datetime.replace(day=7, hour=7, minute=0),
                start_temp=20.0,
                end_temp=20.0,  # 0.0°C/h — excluded
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 6)

        assert result is not None
        # Only the positive cycle (2.0°C/h) should count
        assert result == pytest.approx(2.0, abs=0.01)

    def test_contextual_lhs_excludes_negative_slope_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that cycles with negative slope (cooling) are excluded.

        Negative slope means temperature decreased — not useful for learning.
        Only positive-slope cycles contribute to the average.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                end_time=base_datetime.replace(hour=7, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2.0°C/h — included
            ),
            self._create_cycle(
                start_time=base_datetime.replace(day=7, hour=6, minute=0),
                end_time=base_datetime.replace(day=7, hour=7, minute=0),
                start_temp=20.0,
                end_temp=18.0,  # -2.0°C/h — excluded
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 6)

        assert result is not None
        # Only the positive cycle (2.0°C/h) should count
        assert result == pytest.approx(2.0, abs=0.01)

    # ===== Test: Type Hints and Method Signatures =====

    def test_calculate_all_return_type_annotation(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that calculate_all returns correct type dict[int, float | None].

        RED: Type hint enforcement.
        """
        cycles = [self._create_cycle(base_datetime)]
        result = service.calculate_all_contextual_lhs(cycles)

        assert isinstance(result, dict)
        # All keys should be int
        assert all(isinstance(k, int) for k in result)
        # All values should be float or None
        assert all(isinstance(v, (float, type(None))) for v in result.values())

    def test_calculate_for_hour_return_type_annotation(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that calculate_contextual_lhs_for_hour returns float | None.

        RED: Type hint enforcement.
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=6),
            start_temp=18.0,
            end_temp=20.0,
        )

        result = service.calculate_contextual_lhs_for_hour([cycle], 6)

        assert isinstance(result, (float, type(None)))

    # ===== Test: Large Data Set =====

    def test_calculate_all_with_365_days_of_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculation with one year of daily cycles.

        RED: Large dataset handling.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime + timedelta(days=i, hours=6),
                start_temp=18.0,
                end_temp=20.0,
            )
            for i in range(365)
        ]

        result = service.calculate_all_contextual_lhs(cycles)

        # Hour 6 should have ~52 cycles (365/7 weeks)
        # Average should stabilize around 2.0°C/h
        assert result[6] is not None
        assert result[6] == pytest.approx(2.0, abs=0.01)

    def test_calculate_all_with_cycles_spread_all_24_hours(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test when cycles exist for all 24 hours.

        RED: No hours should have None value.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=h),
                start_temp=18.0,
                end_temp=20.0,
            )
            for h in range(24)
        ]

        result = service.calculate_all_contextual_lhs(cycles)

        # All 24 hours should have data
        assert all(result[h] is not None for h in range(24))
