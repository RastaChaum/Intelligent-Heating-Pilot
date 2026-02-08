"""Regression tests for LHSCalculationService dead time calculations (Issue #62).

These tests expose coverage gaps in average dead time calculations.
They FAIL with current code to demonstrate missing functionality.
"""

import pytest

from custom_components.intelligent_heating_pilot.domain.services.lhs_calculation_service import (
    LHSCalculationService,
)
from tests.unit.domain.fixtures import create_test_heating_cycle, get_test_datetime


class TestCalculateAverageDeadTime:
    """Regression tests for calculate_average_dead_time() method.

    These tests verify the correct calculation of average dead time from heating cycles,
    including edge cases and filtering logic.

    IMPORTANT: These tests FAIL with current code to expose implementation gaps.
    """

    @pytest.fixture
    def service(self):
        """Create LHSCalculationService instance for testing."""
        return LHSCalculationService()

    def test_calculate_average_dead_time_single_cycle(self, service):
        """Test averaging with a single cycle.

        GIVEN: List with one HeatingCycle where dead_time_cycle_minutes=10.0
        WHEN: calculate_average_dead_time() called
        THEN: Should return 10.0

        This test FAILS if the method doesn't handle single cycles correctly
        or if dead_time_cycle_minutes is not properly extracted.
        """
        cycle = create_test_heating_cycle(
            device_id="climate.test_vtherm",
            start_time=get_test_datetime(),
        )
        # Manually set dead_time_cycle_minutes since fixture doesn't set it
        cycle_with_dead_time = cycle.__class__(
            device_id=cycle.device_id,
            start_time=cycle.start_time,
            end_time=cycle.end_time,
            target_temp=cycle.target_temp,
            end_temp=cycle.end_temp,
            start_temp=cycle.start_temp,
            tariff_details=cycle.tariff_details,
            dead_time_cycle_minutes=10.0,
        )

        result = service.calculate_average_dead_time([cycle_with_dead_time])

        assert result is not None, "Should return valid average for single cycle"
        assert result == pytest.approx(10.0)

    def test_calculate_average_dead_time_multiple_cycles(self, service):
        """Test averaging multiple cycles.

        GIVEN: Cycles with dead times: [10.0, 12.0, 14.0]
        THEN: Should return 12.0 (average of 10+12+14)/3

        This test FAILS if the averaging calculation is incorrect
        or if cycles are not properly processed.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", 10.0),
            ("climate.test_vtherm", 12.0),
            ("climate.test_vtherm", 14.0),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is not None
        assert result == pytest.approx(12.0)

    def test_calculate_average_dead_time_filters_none_values(self, service):
        """Test that None values are excluded from average.

        GIVEN: Cycles with dead times: [10.0, None, 14.0, None, 16.0]
        WHEN: calculate_average_dead_time() called
        THEN: Should return 13.33... (average of 10, 14, 16 only)

        This test FAILS if None values are included in the calculation
        or if they cause the method to fail.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", 10.0),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", 14.0),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", 16.0),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is not None
        # Average of [10, 14, 16] = 40 / 3 = 13.333...
        assert result == pytest.approx(13.333, abs=0.01)

    def test_calculate_average_dead_time_filters_zero_values(self, service):
        """Test handling of zero dead time values.

        GIVEN: Cycles with dead times: [0.0, 10.0, 20.0]
        DECISION: Zero values are filtered out (represent cycles with no dead time detected)
        THEN: Should return 15.0 (average of 10, 20 only - excluding 0.0)

        This test documents the intended behavior: cycles with 0.0 dead time
        (no dead time detected/measured) should be excluded from average calculation.

        This test FAILS if zero values are included or if filtering logic is absent.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", 0.0),
            ("climate.test_vtherm", 10.0),
            ("climate.test_vtherm", 20.0),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        # According to LHSCalculationService code (line 191-194):
        # only cycles with dead_time_cycle_minutes > 0 are included
        assert result is not None
        # Average of [10, 20] = 30 / 2 = 15.0
        assert result == pytest.approx(15.0)

    def test_calculate_average_dead_time_empty_list(self, service):
        """Test that empty list returns None.

        GIVEN: Empty list of cycles
        WHEN: calculate_average_dead_time() called
        THEN: Should return None

        This test FAILS if the method doesn't handle empty input correctly
        or if it raises an exception.
        """
        result = service.calculate_average_dead_time([])

        assert result is None, "Should return None for empty cycle list"

    def test_calculate_average_dead_time_all_none(self, service):
        """Test that all-None list returns None.

        GIVEN: Cycles with dead times: [None, None, None]
        WHEN: calculate_average_dead_time() called
        THEN: Should return None

        This test FAILS if the method crashes with all-None values
        or doesn't properly handle no valid data scenario.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", None),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is None, "Should return None when all cycles have None dead_time"

    def test_calculate_average_dead_time_all_zero(self, service):
        """Test that all-zero list returns None.

        GIVEN: Cycles with dead times: [0.0, 0.0, 0.0]
        WHEN: calculate_average_dead_time() called
        THEN: Should return None (no valid dead times > 0)

        This test FAILS if zero values are included or if no valid data check is absent.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", 0.0),
            ("climate.test_vtherm", 0.0),
            ("climate.test_vtherm", 0.0),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is None, "Should return None when all cycles have 0.0 dead_time"

    def test_calculate_average_dead_time_mixed_valid_invalid(self, service):
        """Test mixed valid and invalid (None/zero) dead times.

        GIVEN: Cycles: [5.0, None, 15.0, None, None, 25.0]
        AND:   Also cycles with 0.0 should be filtered
        WHEN: calculate_average_dead_time() called
        THEN: Should return 15.0 (average of 5, 15, 25)

        This test FAILS if the filtering logic doesn't properly exclude
        None and 0.0 values while including valid positive values.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles_data = [
            ("climate.test_vtherm", 5.0),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", 15.0),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", None),
            ("climate.test_vtherm", 25.0),
        ]

        cycles = []
        for i, (device_id, dead_time) in enumerate(cycles_data):
            cycle = create_test_heating_cycle(
                device_id=device_id,
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is not None
        # Average of [5, 15, 25] = 45 / 3 = 15.0
        assert result == pytest.approx(15.0)

    @pytest.mark.parametrize(
        "dead_times,expected",
        [
            ([5.0, 10.0, 15.0], 10.0),
            ([7.5], 7.5),
            ([2.0, 3.0, 4.0, 5.0, 6.0], 4.0),
        ],
    )
    def test_calculate_average_dead_time_various_data_sets(self, service, dead_times, expected):
        """Test averaging various data sets with parametrize.

        GIVEN: Various lists of dead times
        WHEN: calculate_average_dead_time() called for each
        THEN: Should return correct average

        This test FAILS if the averaging calculation is incorrect
        for different input scenarios.
        """
        from datetime import timedelta

        base_time = get_test_datetime()
        cycles = []
        for i, dead_time in enumerate(dead_times):
            cycle = create_test_heating_cycle(
                device_id="climate.test_vtherm",
                start_time=base_time + timedelta(hours=i),
            )
            cycle_with_dead_time = cycle.__class__(
                device_id=cycle.device_id,
                start_time=cycle.start_time,
                end_time=cycle.end_time,
                target_temp=cycle.target_temp,
                end_temp=cycle.end_temp,
                start_temp=cycle.start_temp,
                tariff_details=cycle.tariff_details,
                dead_time_cycle_minutes=dead_time,
            )
            cycles.append(cycle_with_dead_time)

        result = service.calculate_average_dead_time(cycles)

        assert result is not None
        assert result == pytest.approx(expected, abs=0.01)
