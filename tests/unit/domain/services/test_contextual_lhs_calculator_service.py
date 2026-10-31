"""Unit tests for ContextualLHSCalculatorService.

Tests the pure domain logic for grouping cycles by the hour their target was
reached (end hour) and calculating contextual heating slopes.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.domain.constants import MINIMUM_REALISTIC_LHS
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
        """Test extracting hour from cycle ending at midnight (hour=0)."""
        cycle = self._create_cycle(
            start_time=base_datetime - timedelta(hours=1),
            end_time=base_datetime,
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 0

    def test_extract_hour_at_morning(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test extracting hour from cycle ending at 06:00."""
        end = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=end - timedelta(hours=1),
            end_time=end,
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 6

    def test_extract_hour_uses_end_time_for_preheat_cycle(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """A preheat cycle for a 07:00 slot that starts at 05:30 is keyed by hour 7.

        The lookup for the slot reads ``target_time.hour`` (7), so the cycle must be
        filed under the hour its target was reached, not the hour it started (#183).
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=5, minute=30),
            end_time=base_datetime.replace(hour=7, minute=2),
        )

        hour = service.extract_hour_from_cycle(cycle)

        assert hour == 7

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

    # ===== group_cycles_by_hour Tests =====

    def test_group_empty_cycles_list(self, service: ContextualLHSCalculatorService) -> None:
        """Test grouping empty cycles list."""
        grouped = service.group_cycles_by_hour([])

        assert len(grouped) == 24
        assert all(v == [] for v in grouped.values())

    def test_group_single_cycle_at_hour_6(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test grouping single cycle ending at hour 6."""
        end = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=end - timedelta(hours=1),
            end_time=end,
        )

        grouped = service.group_cycles_by_hour([cycle])

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

        grouped = service.group_cycles_by_hour(cycles)

        assert len(grouped[7]) == 2
        assert len(grouped[13]) == 1
        assert len(grouped[21]) == 1
        assert len(grouped[6]) == 0

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
        end = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=end - timedelta(hours=1),
            end_time=end,
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

        result = service.calculate_contextual_lhs_for_hour([cycle1, cycle2], 7)

        assert result is not None
        assert abs(result - 14.75) < 0.01

    def test_calculate_lhs_three_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test calculating LHS with three cycles."""
        cycles = []
        for day in range(3):
            end = (base_datetime - timedelta(days=day)).replace(hour=6)
            cycle = self._create_cycle(
                start_time=end - timedelta(hours=1),
                end_time=end,
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
        end = base_datetime.replace(hour=6)
        cycle = self._create_cycle(
            start_time=end - timedelta(hours=1),
            end_time=end,
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
            end = base_datetime.replace(hour=hour)
            cycle = self._create_cycle(
                start_time=end - timedelta(hours=1),
                end_time=end,
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

    # ===== Test: Non-positive slope filtering =====

    def test_contextual_lhs_excludes_zero_slope_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that zero-slope cycles are excluded from contextual LHS average.

        Zero slope means no actual heating occurred — not useful for learning.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=15.0,
                end_temp=18.0,  # 3.0°C/h
            ),
            self._create_cycle(
                start_time=(base_datetime + timedelta(days=1)).replace(hour=6),
                end_time=(base_datetime + timedelta(days=1)).replace(hour=7),
                start_temp=18.0,
                end_temp=18.0,  # 0.0°C/h — should be excluded
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 7)

        # Only the positive cycle (3.0°C/h) should count
        assert result is not None
        assert result == pytest.approx(3.0, abs=0.01)

    def test_contextual_lhs_excludes_negative_slope_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that negative-slope cycles are excluded from contextual LHS average."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=15.0,
                end_temp=18.0,  # 3.0°C/h
            ),
            self._create_cycle(
                start_time=(base_datetime + timedelta(days=1)).replace(hour=6),
                end_time=(base_datetime + timedelta(days=1)).replace(hour=7),
                start_temp=20.0,
                end_temp=18.0,  # -2.0°C/h — should be excluded
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 7)

        assert result is not None
        assert result == pytest.approx(3.0, abs=0.01)

    def test_contextual_lhs_returns_none_when_all_slopes_non_positive(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Test that None is returned when all cycles for an hour have slope <= 0."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=20.0,  # 0.0°C/h
            ),
            self._create_cycle(
                start_time=(base_datetime + timedelta(days=1)).replace(hour=6),
                end_time=(base_datetime + timedelta(days=1)).replace(hour=7),
                start_temp=20.0,
                end_temp=18.0,  # -2.0°C/h
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 7)

        assert result is None

    def test_contextual_lhs_returns_none_when_average_below_realistic_minimum(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """An average below MINIMUM_REALISTIC_LHS is not learned, so callers use global (#184)."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=20.15,  # 0.15°C/h
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 7)

        assert result is None

    def test_contextual_lhs_keeps_slow_but_realistic_average(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """A slow average just above MINIMUM_REALISTIC_LHS is still a learned value."""
        slow_slope = MINIMUM_REALISTIC_LHS + 0.05
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=20.0 + slow_slope,
            ),
        ]

        result = service.calculate_contextual_lhs_for_hour(cycles, 7)

        assert result == pytest.approx(slow_slope, abs=0.001)

    def test_contextual_lhs_excludes_unrealistic_cycle_from_hour_average(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """An unrealistic cycle is left out of its hour, like in the global LHS (#223)."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=17.0,
                end_temp=20.0,  # 3.0°C/h
            ),
            self._create_cycle(
                start_time=(base_datetime + timedelta(days=1)).replace(hour=6),
                end_time=(base_datetime + timedelta(days=1)).replace(hour=7),
                start_temp=20.0,
                end_temp=20.1,  # 0.1°C/h — unrealistic, excluded
            ),
        ]

        assert service.calculate_contextual_lhs_for_hour(cycles, 7) == pytest.approx(3.0)
        assert service.calculate_contextual_lhs_by_hour(cycles).learned[7] == pytest.approx(3.0)

    def test_contextual_lhs_by_hour_does_not_reject_hour_without_heating(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """An hour whose cycles never heated has no data; it is not reported as rejected."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=20.0,  # 0.0°C/h
            ),
        ]

        result = service.calculate_contextual_lhs_by_hour(cycles)

        assert 7 not in result.learned
        assert 7 not in result.rejected_hours

    def test_calculate_all_contextual_lhs_reports_unrealistic_hour_as_none(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """The bulk write path never persists an unrealistic hour."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=20.1,  # 0.1°C/h
            ),
        ]

        result = service.calculate_all_contextual_lhs(cycles)

        assert result[7] is None

    def test_contextual_lhs_by_hour_separates_rejected_hours_from_hours_without_cycles(
        self, service: ContextualLHSCalculatorService, base_datetime: datetime
    ) -> None:
        """Rejected hours are reported apart, so callers can drop their stored slope (#184)."""
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6),
                end_time=base_datetime.replace(hour=7),
                start_temp=20.0,
                end_temp=22.0,  # 2.0°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=21),
                end_time=base_datetime.replace(hour=22),
                start_temp=20.0,
                end_temp=20.1,  # 0.1°C/h
            ),
        ]

        result = service.calculate_contextual_lhs_by_hour(cycles)

        assert result.learned == {7: pytest.approx(2.0, abs=0.001)}
        assert result.rejected_hours == frozenset({22})
        assert result.as_hour_map()[22] is None
        assert result.as_hour_map()[12] is None

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


class TestContextualHourTimezone:
    """Cycle times are naive UTC; slots are looked up in local time (#183)."""

    def test_naive_utc_end_time_is_converted_to_local_hour(self) -> None:
        """A cycle ending 05:00 UTC serves the 07:00 slot in UTC+2."""
        service = ContextualLHSCalculatorService(local_tz=timezone(timedelta(hours=2)))
        cycle = HeatingCycle(
            device_id="test_device",
            start_time=datetime(2025, 2, 9, 3, 30),
            end_time=datetime(2025, 2, 9, 5, 0),
            target_temp=20.0,
            end_temp=20.0,
            start_temp=17.0,
        )

        assert service.extract_hour_from_cycle(cycle) == 7

    def test_nearest_hour_is_taken_on_the_local_clock(self) -> None:
        """A cycle ending 04:58 UTC reached the target at 06:58 in UTC+2: hour 7 (#214)."""
        service = ContextualLHSCalculatorService(local_tz=timezone(timedelta(hours=2)))
        cycle = HeatingCycle(
            device_id="test_device",
            start_time=datetime(2025, 2, 9, 3, 30),
            end_time=datetime(2025, 2, 9, 4, 58),
            target_temp=20.0,
            end_temp=20.0,
            start_temp=17.0,
        )

        assert service.extract_hour_from_cycle(cycle) == 7


class TestContextualHourOfCycleEnd:
    """A cycle is filed under the hour nearest to its end (#214)."""

    @pytest.fixture
    def service(self) -> ContextualLHSCalculatorService:
        """Create service instance."""
        return ContextualLHSCalculatorService()

    @staticmethod
    def _cycle_ending_at(hour: int, minute: int) -> HeatingCycle:
        end_time = datetime(2025, 2, 9, hour, minute, tzinfo=UTC)
        return HeatingCycle(
            device_id="test_device",
            start_time=end_time - timedelta(hours=1),
            end_time=end_time,
            target_temp=20.0,
            end_temp=20.0,
            start_temp=17.0,
        )

    def test_cycle_ending_just_before_the_hour_is_filed_under_that_hour(
        self, service: ContextualLHSCalculatorService
    ) -> None:
        """A preheat that reaches the target at 06:58 served the 07:00 slot."""
        assert service.extract_hour_from_cycle(self._cycle_ending_at(6, 58)) == 7

    def test_cycle_ending_on_the_half_hour_stays_in_the_earlier_hour(
        self, service: ContextualLHSCalculatorService
    ) -> None:
        """A cycle ending exactly at 06:30 counts for a 06:30 slot, which reads hour 6."""
        assert service.extract_hour_from_cycle(self._cycle_ending_at(6, 30)) == 6

    def test_cycle_ending_just_before_midnight_is_filed_under_hour_0(
        self, service: ContextualLHSCalculatorService
    ) -> None:
        """The hour after 23 wraps to 0 instead of leaving the 0-23 range."""
        assert service.extract_hour_from_cycle(self._cycle_ending_at(23, 50)) == 0

    def test_hour_slope_averages_cycles_landing_around_the_slot(
        self, service: ContextualLHSCalculatorService
    ) -> None:
        """Cycles reaching the target at 06:58 and 07:20 both teach hour 7."""
        early = self._cycle_ending_at(6, 58)  # 3.0 °C/h
        late = replace(self._cycle_ending_at(7, 20), end_temp=21.0)  # 4.0 °C/h

        assert service.calculate_contextual_lhs_for_hour([early, late], 7) == pytest.approx(3.5)
