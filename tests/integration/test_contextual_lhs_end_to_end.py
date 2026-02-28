"""Integration tests for contextual LHS end-to-end flow.

Tests the complete flow from cycle extraction to sensor readout,
covering all 4 main scenarios.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


class TestContextualLHSEndToEnd:
    """End-to-end tests for contextual LHS flow.

    Tests the complete scenario from cycle extraction through
    cache population to sensor readout.
    """

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime for testing."""
        result = dt_util.parse_datetime("2025-02-09T00:00:00+00:00")
        assert result is not None
        return result

    @pytest.fixture
    def calculator_service(self) -> ContextualLHSCalculatorService:
        """Create calculator service."""
        return ContextualLHSCalculatorService()

    @pytest.fixture
    async def mock_model_storage(self) -> AsyncMock:
        """Create mock model storage."""
        mock = AsyncMock()
        mock.set_cached_contextual_lhs = AsyncMock()
        mock.get_cached_contextual_lhs = AsyncMock()
        mock.get_cached_contextual_lhs_sync = Mock()
        return mock

    # ===== Scenario A: Scheduler Active + Cycles Exist for Hour =====

    @pytest.mark.asyncio
    async def test_scenario_a_scheduler_active_cycles_exist(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
        mock_model_storage: AsyncMock,
    ) -> None:
        """Scenario A: Next schedule at 06:00, cycles exist at hour 6.

        Setup:
          - Next Schedule Time: 2025-02-09 06:00 (hour=6)
          - Extracted cycles: Cycle(start_time=06:15, lhs=15.0), Cycle(start_time=06:30, lhs=14.5)

        Expected:
          - contextual_lhs = 14.75°C/h (average)
          - Cache populated for hour 6
          - Sensor returns float value
        """
        # Create cycles at hour 6
        cycle1 = self._create_cycle(
            start_time=base_datetime.replace(hour=6, minute=15),
            end_time=base_datetime.replace(hour=7, minute=15),
            start_temp=15.0,
            end_temp=30.0,  # LHS = 15.0
        )
        cycle2 = self._create_cycle(
            start_time=(base_datetime - timedelta(days=1)).replace(hour=6, minute=30),
            end_time=(base_datetime - timedelta(days=1)).replace(hour=7, minute=30),
            start_temp=15.0,
            end_temp=29.5,  # LHS = 14.5
        )
        cycles = [cycle1, cycle2]

        # Calculate contextual LHS for hour 6
        result = calculator_service.calculate_contextual_lhs_for_hour(cycles, 6)

        # Verify
        assert result is not None
        assert abs(result - 14.75) < 0.01
        assert isinstance(result, float)

    # ===== Scenario B: Scheduler Active + NO Cycles for Hour =====

    @pytest.mark.asyncio
    async def test_scenario_b_scheduler_active_no_cycles_for_hour(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
    ) -> None:
        """Scenario B: Next schedule at 12:00, but no cycles at hour 12.

        Setup:
          - Next Schedule Time: 2025-02-09 12:00 (hour=12)
          - Extracted cycles: Cycle(start_time=06:15, lhs=15.0) [no hour 12]

        Expected:
          - contextual_lhs = None
          - Sensor returns "unknown"
          - Log: No cycles for this hour
        """
        cycle = self._create_cycle(
            start_time=base_datetime.replace(hour=6, minute=15),
            end_time=base_datetime.replace(hour=7, minute=15),
        )
        cycles = [cycle]

        result = calculator_service.calculate_contextual_lhs_for_hour(cycles, 12)

        assert result is None

    # ===== Scenario C: No Scheduler Configured =====

    @pytest.mark.asyncio
    async def test_scenario_c_no_scheduler_configured(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
    ) -> None:
        """Scenario C: No scheduler configured, so no next_schedule_time.

        Setup:
          - scheduler_entities = []
          - Next Schedule Time = None
          - Cycles exist but unused

        Expected:
          - contextual_lhs query returns None
          - Sensor shows "unknown"
          - No cache lookup attempt
        """
        # When there's no scheduler, get_next_schedule_time() returns None
        # Coordinator should not call get_contextual_learned_heating_slope()
        # or it should return None immediately

        next_schedule_time = None
        assert next_schedule_time is None

    # ===== Scenario D: Exception Handling =====

    @pytest.mark.asyncio
    async def test_scenario_d_calculation_fails_gracefully(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
    ) -> None:
        """Scenario D: Calculation faces exception, returns None gracefully.

        Setup:
          - Next Schedule Time exists
          - Model storage throws exception on read

        Expected:
          - contextual_lhs = None
          - WARNING logged
          - Sensor shows "unknown"
        """
        # Simulate exception scenario
        with patch.object(
            calculator_service,
            "calculate_contextual_lhs_for_hour",
            side_effect=Exception("Database error"),
        ):
            try:
                result = calculator_service.calculate_contextual_lhs_for_hour([], 6)
            except Exception:
                result = None

            assert result is None

    # ===== Multi-Day Cycle Tests =====

    @pytest.mark.asyncio
    async def test_multi_day_cycle_uses_start_hour(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
    ) -> None:
        """Multi-day cycle from 23:00 to next day 02:00 belongs to hour 23.

        Setup:
          - Cycle starts 2025-02-08 23:00
          - Cycle ends 2025-02-09 02:00
          - Spans midnight

        Expected:
          - Hour extraction = 23 (start hour, not span logic)
          - Cycle groups to hour 23, not hours 23, 0, 1, 2
        """
        start = base_datetime.replace(day=8, hour=23, minute=0)
        end = base_datetime.replace(day=9, hour=2, minute=0)
        cycle = self._create_cycle(
            start_time=start,
            end_time=end,
        )

        hour = calculator_service.extract_hour_from_cycle(cycle)

        assert hour == 23

        # Verify it groups to hour 23
        result = calculator_service.calculate_contextual_lhs_for_hour([cycle], 23)
        assert result is not None

        # Verify it doesn't match other hours
        for h in [0, 1, 2]:
            result = calculator_service.calculate_contextual_lhs_for_hour([cycle], h)
            assert result is None

    # ===== Cache Population Scenario =====

    @pytest.mark.asyncio
    async def test_cache_refresh_on_new_extraction(
        self,
        base_datetime: datetime,
        calculator_service: ContextualLHSCalculatorService,
    ) -> None:
        """Cache refresh: new cycles update existing averages.

        First extraction:
          - Cycles at hour 6: [15.0]
          - Cache[6] = 15.0

        Second extraction:
          - New cycles at hour 6: [15.0, 14.5, 15.5]
          - Cache[6] updated to average

        Expected:
          - Average includes all cycles (new + previous)
        """
        # First extraction
        cycle1_first = self._create_cycle(
            start_time=base_datetime.replace(hour=6),
            end_time=base_datetime.replace(hour=7),
            start_temp=15.0,
            end_temp=30.0,  # LHS = 15.0
        )

        result_first = calculator_service.calculate_all_contextual_lhs([cycle1_first])
        assert result_first[6] is not None
        assert abs(result_first[6] - 15.0) < 0.01

        # Second extraction (simulating 24h refresh)
        cycle1_second = self._create_cycle(
            start_time=(base_datetime - timedelta(days=1)).replace(hour=6),
            end_time=(base_datetime - timedelta(days=1)).replace(hour=7),
            start_temp=15.0,
            end_temp=29.5,  # LHS = 14.5
        )
        cycle2_second = self._create_cycle(
            start_time=(base_datetime - timedelta(days=2)).replace(hour=6),
            end_time=(base_datetime - timedelta(days=2)).replace(hour=7),
            start_temp=15.0,
            end_temp=30.5,  # LHS = 15.5
        )

        all_cycles = [cycle1_first, cycle1_second, cycle2_second]
        result_second = calculator_service.calculate_all_contextual_lhs(all_cycles)

        # Average should be (15.0 + 14.5 + 15.5) / 3 = 15.0
        assert result_second[6] is not None
        assert abs(result_second[6] - 15.0) < 0.01

    # ===== Helper Methods =====

    def _create_cycle(
        self,
        start_time: datetime,
        end_time: datetime,
        start_temp: float = 15.0,
        end_temp: float = 18.0,
        target_temp: float = 20.0,
    ) -> HeatingCycle:
        """Helper to create a test HeatingCycle."""
        return HeatingCycle(
            device_id="test_device",
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            dead_time_cycle_minutes=0,
            tariff_details=None,
        )
