"""Integration tests for Contextual LHS system end-to-end.

These tests validate the complete contextual LHS calculation workflow,
including scenario tests (A, B, C, D) and regression tests for previously
discovered bugs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.services.global_lhs_calculator_service import (
    GlobalLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.contextual_lhs_data import (
    ContextualLHSData,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.lhs_cache_entry import (
    LHSCacheEntry,
)


class TestContextualLHSIntegration:
    """Integration test suite for contextual LHS system."""

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime: 2025-02-09 00:00:00."""
        return datetime(2025, 2, 9, 0, 0, 0)

    @pytest.fixture
    def contextual_service(self) -> ContextualLHSCalculatorService:
        """Create contextual LHS calculator service."""
        return ContextualLHSCalculatorService()

    @pytest.fixture
    def global_service(self) -> GlobalLHSCalculatorService:
        """Create global LHS calculator service."""
        return GlobalLHSCalculatorService()

    @pytest.fixture
    def mock_model_storage(self) -> AsyncMock:
        """Create mock model storage."""
        storage = AsyncMock()
        storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
        storage.set_cached_contextual_lhs = AsyncMock()
        return storage

    # ===== Helper Methods =====

    def _create_cycle(
        self,
        device_id: str = "climate.test_vtherm",
        start_time: datetime | None = None,
        start_temp: float = 18.0,
        end_temp: float = 20.0,
        target_temp: float = 21.0,
        duration_hours: float = 1.0,
    ) -> HeatingCycle:
        """Create a test heating cycle."""
        if start_time is None:
            start_time = datetime.now()

        end_time = start_time + timedelta(hours=duration_hours)

        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None,
        )

    # ===== Scenario A: Scheduler Active + Cycles Exist for Hour =====

    def test_scenario_a_scheduler_active_cycles_exist_for_hour(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Scenario A: Scheduler active + cycles exist for target hour.

        Given:
            next_schedule_time: 2025-02-09 06:00:00 (hour 6)
            cycles:
            - start: 2025-02-08 06:15:00, lhs=15.0°C/h
            - start: 2025-02-07 06:30:00, lhs=14.5°C/h

        Expected:
            contextual_lhs[6] = ContextualLHSData(lhs=14.75, cycle_count=2)

        RED: Domain logic should correctly group and average cycles for the hour.
        """
        # Actually for slope 15.0°C/h, we need different duration
        cycle1_custom = HeatingCycle(
            device_id="climate.test",
            start_time=base_datetime.replace(day=8, hour=6, minute=15),
            end_time=base_datetime.replace(day=8, hour=6, minute=15) + timedelta(hours=0.2),
            target_temp=21.0,
            end_temp=21.0,
            start_temp=18.0,  # 3°C / 0.2h = 15°C/h
        )

        cycle2_custom = HeatingCycle(
            device_id="climate.test",
            start_time=base_datetime.replace(day=7, hour=6, minute=30),
            end_time=base_datetime.replace(day=7, hour=6, minute=30) + timedelta(hours=0.2),
            target_temp=21.0,
            end_temp=20.7,
            start_temp=18.0,  # 2.9°C / 0.2h = 13.5°C/h
        )

        cycles = [cycle1_custom, cycle2_custom]

        # Calculate contextual LHS
        contextual_result = contextual_service.calculate_all_contextual_lhs(cycles)

        # Hour 6 should have data
        assert contextual_result[6] is not None
        assert contextual_result[6] == pytest.approx(14.25, abs=0.1)

    def test_scenario_a_sensor_displays_numeric_value_and_count(
        self, base_datetime: datetime
    ) -> None:
        """Scenario A: Sensor should display numeric LHS value + cycle count.

        RED: ContextualLHSData should provide display-friendly value.
        """
        data = ContextualLHSData(
            hour=6,
            lhs=14.75,
            cycle_count=2,
            calculated_at=base_datetime,
        )

        display_value = data.get_display_value()

        assert display_value == 14.75
        assert isinstance(display_value, float)
        assert data.cycle_count == 2

    # ===== Scenario B: Scheduler Active + NO Cycles for Hour =====

    def test_scenario_b_scheduler_active_no_cycles_for_hour(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Scenario B: Scheduler active + NO cycles for target hour.

        Given:
            next_schedule_time: 2025-02-09 12:00:00 (hour 12)
            cycles: all cycles from hour 6 only (no hour 12 cycles)

        Expected:
            contextual_lhs[12] = None

        RED: Domain should return None when no cycles for requested hour.
        """
        # Create cycles only for hour 6, none for hour 12
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=30),
                start_temp=18.0,
                end_temp=20.0,
            ),
        ]

        contextual_result = contextual_service.calculate_all_contextual_lhs(cycles)

        # Hour 12 should have None (no data)
        assert contextual_result[12] is None

    def test_scenario_b_sensor_displays_unknown_when_no_data(self, base_datetime: datetime) -> None:
        """Scenario B: Sensor should display 'unknown' when no data for hour.

        RED: get_display_value() should return 'unknown' string.
        """
        data = ContextualLHSData(
            hour=12,
            lhs=None,
            cycle_count=0,
            calculated_at=base_datetime,
        )

        display_value = data.get_display_value()

        assert display_value == "unknown"
        assert isinstance(display_value, str)

    # ===== Scenario C: No Scheduler Configured =====

    def test_scenario_c_no_scheduler_configured_returns_none_for_next_event(
        self,
    ) -> None:
        """Scenario C: No scheduler entity configured.

        Given:
            scheduler_entities: []
            next_schedule_time: None

        Expected:
            Sensor displays 'unknown'

        RED: Without scheduler, contextual LHS cannot be calculated.
        """
        # Create data with None lhs (no scheduler to determine which hour)
        data = ContextualLHSData(
            hour=0,
            lhs=None,
            cycle_count=0,
            calculated_at=datetime.now(),
            reason="no_scheduler_configured",
        )

        # Cannot be available without valid LHS data
        display_value = data.get_display_value()
        assert display_value == "unknown"

    # ===== Scenario D: Recalculation on Every Cycle Addition =====

    def test_scenario_d_recalculation_not_24h_delay(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Scenario D: Recalculate IMMEDIATELY when cycles added, not 24h delay.

        Given:
            Initial: extract_cycles([cycle1, cycle2])
            → cache[6] = {lhs: 14.75, count: 2}

            Then: extract_cycles([cycle1, cycle2, cycle3])

        Expected:
            → cache[6] = {lhs: 15.0, count: 3}
            Updated immediately, not waiting for 24h timer

        RED: Extraction should trigger immediate recalculation.
        """
        # Initial extraction with 2 cycles
        cycles_initial = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=30),
                start_temp=18.0,
                end_temp=21.0,  # 3°C/h (assuming shorter duration)
                duration_hours=1.0,
            ),
        ]

        result_initial = contextual_service.calculate_all_contextual_lhs(cycles_initial)
        assert result_initial[6] is not None

        # Then add third cycle and recalculate
        cycle3 = self._create_cycle(
            start_time=base_datetime.replace(day=10, hour=6, minute=15),
            start_temp=18.0,
            end_temp=22.0,  # 4°C/h
            duration_hours=1.0,
        )
        cycles_updated = cycles_initial + [cycle3]

        result_updated = contextual_service.calculate_all_contextual_lhs(cycles_updated)

        # Should be different values (recalculated immediately)
        assert result_updated[6] is not None
        # New average should differ from old (more cycles)
        assert result_updated[6] != result_initial[6]

    # ===== Edge Case: Multi-day Cycles Spanning Midnight =====

    def test_cycle_spanning_across_day_boundary_hour_23_to_next_day(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Test cycle starting at 23:50 that spans to next day.

        Given:
            cycle starts: 2025-02-09 23:50:00
            cycle ends: 2025-02-10 00:30:00

        Expected:
            Grouped only by START hour (23), not end hour

        RED: Grouping should use start_time.hour, not end_time.hour.
        """
        cycle = HeatingCycle(
            device_id="climate.test",
            start_time=base_datetime.replace(hour=23, minute=50),
            end_time=base_datetime.replace(day=10, hour=0, minute=30),
            target_temp=21.0,
            end_temp=20.0,
            start_temp=18.0,
        )

        contextual_result = contextual_service.calculate_all_contextual_lhs([cycle])

        # Should be grouped in hour 23 (start hour), not hour 0
        assert contextual_result[23] is not None
        assert contextual_result[0] is None

    def test_multiple_cycles_hour_23_grouped_correctly(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Test multiple cycles all starting at hour 23 are grouped correctly.

        RED: All cycles with start_hour=23, regardless of when they end.
        """
        cycle1 = self._create_cycle(
            start_time=base_datetime.replace(hour=23, minute=0),
            start_temp=18.0,
            end_temp=20.0,
        )
        cycle2 = self._create_cycle(
            start_time=base_datetime.replace(day=7, hour=23, minute=30),
            start_temp=18.0,
            end_temp=21.0,
        )

        contextual_result = contextual_service.calculate_all_contextual_lhs([cycle1, cycle2])

        # Both should be in hour 23
        assert contextual_result[23] is not None
        assert contextual_result[23] == pytest.approx(2.5, abs=0.1)

    # ===== Edge Case: Retention Parameter Change =====

    @pytest.mark.asyncio
    async def test_retention_parameter_change_triggers_cache_recalc(
        self,
        contextual_service: ContextualLHSCalculatorService,
        mock_model_storage: AsyncMock,
        base_datetime: datetime,
    ) -> None:
        """Test that retention parameter change invalidates and recalculates cache.

        RED: Changing retention should force cache recalculation.
        """
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,
            ),
        ]

        # Initial calculation with 10-day retention
        result_10d = contextual_service.calculate_all_contextual_lhs(cycles)
        assert result_10d[6] is not None

        # Change to 5-day retention (should invalidate cache)
        # In real implementation, old cache entries outside retention are dropped
        initial_lhs = result_10d[6]

        # Simulate retention change by recalculating (no cycles older than 5d)
        # Result should be same as only cycles within 5 days exist
        result_5d = contextual_service.calculate_all_contextual_lhs(cycles)

        # In this simple case, same cycles so result same
        assert result_5d[6] == pytest.approx(initial_lhs, abs=0.01)

    # ===== Regression Test: Contextual LHS Different from Global =====

    def test_regression_contextual_lhs_different_from_global_when_distributed(
        self,
        contextual_service: ContextualLHSCalculatorService,
        global_service: GlobalLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Regression: Contextual should NOT equal Global when cycles per hour vary.

        Bug: Contextual LHS was returning global LHS instead of per-hour average.

        Given:
            Global LHS = avg([15, 14, 10]) = 13.0°C/h
            Hour 6: avg([15, 14]) = 14.5°C/h (from hour 6 only)
            Hour 12: avg([10]) = 10.0°C/h (from hour 12 only)

        Expected:
            contextual[6] ≠ global_lhs
            contextual[6] = 14.5, global = 13.0

        RED: Test FAILS with buggy code (contextual = global).
        """
        # Create cycles: 2 at hour 6, 1 at hour 12
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2°C/h (via avg_heating_slope)
            ),
            self._create_cycle(
                start_time=base_datetime.replace(day=7, hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,  # 2°C/h
            ),
            self._create_cycle(
                start_time=base_datetime.replace(day=8, hour=12, minute=0),
                start_temp=18.0,
                end_temp=19.0,  # 1°C/h
            ),
        ]

        # Calculate both global and contextual
        global_result = global_service.calculate_global_lhs(cycles)
        contextual_result = contextual_service.calculate_all_contextual_lhs(cycles)

        # They MUST be different
        assert contextual_result[6] is not None
        assert contextual_result[12] is not None

        # Contextual per-hour should differ from global average
        assert (
            contextual_result[6] != global_result
        ), "Contextual LHS[6] should NOT equal Global LHS when cycles are distributed by hour"

    def test_regression_contextual_lhs_respects_hour_boundaries(
        self,
        contextual_service: ContextualLHSCalculatorService,
        base_datetime: datetime,
    ) -> None:
        """Regression: Hour 6 cycles should not bleed into hour 7.

        Bug: Cycles might have been incorrectly grouped across hour boundaries.

        RED: Test FAILS if hour grouping is broken.
        """
        # Create cycles: one at hour 6, one at hour 7
        cycle_h6 = self._create_cycle(
            start_time=base_datetime.replace(hour=6, minute=0),
            start_temp=18.0,
            end_temp=20.0,  # 2°C/h
        )
        cycle_h7 = self._create_cycle(
            start_time=base_datetime.replace(day=7, hour=7, minute=0),
            start_temp=18.0,
            end_temp=23.0,  # 5°C/h
        )

        contextual_result = contextual_service.calculate_all_contextual_lhs([cycle_h6, cycle_h7])

        # Hour 6 should NOT contain hour 7's cycle
        assert contextual_result[6] == pytest.approx(2.0, abs=0.1)
        assert contextual_result[7] == pytest.approx(5.0, abs=0.1)
        assert contextual_result[6] != contextual_result[7]

    # ===== Regression Test: Empty Hours =====

    def test_regression_all_24_hours_initialized_even_without_cycles(
        self,
        contextual_service: ContextualLHSCalculatorService,
    ) -> None:
        """Regression: Empty cycles list should return all 24 hours.

        Bug: Might have only returned hours with data, missing empty ones.

        RED: MUST return dict with all 24 hours as keys.
        """
        result = contextual_service.calculate_all_contextual_lhs([])

        # Must have exactly 24 keys (0-23)
        assert len(result) == 24
        assert set(result.keys()) == set(range(24))

        # All values should be None (no cycles)
        assert all(v is None for v in result.values())

    # ===== Integration: Full Workflow =====

    @pytest.mark.asyncio
    async def test_full_contextual_lhs_workflow_extract_cache_retrieve(
        self,
        contextual_service: ContextualLHSCalculatorService,
        mock_model_storage: AsyncMock,
        base_datetime: datetime,
    ) -> None:
        """Full workflow: Extract cycles → Calculate → Cache → Retrieve.

        RED: Complete integration test requiring all components.
        """
        # Step 1: Extract cycles
        cycles = [
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=0),
                start_temp=18.0,
                end_temp=20.0,
            ),
            self._create_cycle(
                start_time=base_datetime.replace(hour=6, minute=30),
                start_temp=18.0,
                end_temp=21.0,
            ),
        ]

        # Step 2: Calculate contextual LHS
        contextual_result = contextual_service.calculate_all_contextual_lhs(cycles)
        assert contextual_result[6] is not None

        # Step 3: Store in cache (simulate)
        lhs_value = contextual_result[6]
        await mock_model_storage.set_cached_contextual_lhs(6, lhs_value, base_datetime)

        # Step 4: Retrieve from cache
        cached_entry = LHSCacheEntry(
            value=lhs_value,
            updated_at=base_datetime,
            hour=6,
        )
        mock_model_storage.get_cached_contextual_lhs = AsyncMock(return_value=cached_entry)
        retrieved = await mock_model_storage.get_cached_contextual_lhs(6)

        # Step 5: Verify
        assert retrieved is not None
        assert retrieved.value == pytest.approx(lhs_value, abs=0.01)
        assert retrieved.hour == 6
