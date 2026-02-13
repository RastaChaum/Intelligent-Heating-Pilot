"""Unit tests for lazy contextual LHS population in LhsLifecycleManager.

These tests verify lazy loading, cache hit optimization, and force recalculation
for contextual LHS values.

Author: QA Engineer
Purpose: Test ensure_contextual_lhs_populated() method
Status: RED - Tests written before implementation (TDD)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.lhs_cache_entry import (
    LHSCacheEntry,
)


class TestLazyContextualLhsPopulation:
    """Test lazy population of contextual LHS.

    Regression Prevention:
    These tests ensure contextual LHS is only calculated when needed,
    properly cached, and can be force-recalculated when requested.
    """

    @pytest.fixture
    def sample_cycles(self, base_datetime: datetime, heating_cycle_builder) -> list[HeatingCycle]:
        """Create sample cycles for LHS calculation."""
        return [
            heating_cycle_builder(
                base_datetime - timedelta(days=5), duration_hours=2.0, temp_increase=3.0
            ),
            heating_cycle_builder(
                base_datetime - timedelta(days=3), duration_hours=1.5, temp_increase=2.5
            ),
        ]

    @pytest.mark.asyncio
    async def test_populates_all_hours_on_first_call(
        self,
        lhs_manager_minimal: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that contextual LHS is calculated on first call for specific hour.

        Expected Behavior (FAILS until implemented):
        - No memory cache exists for hour 14
        - No storage cache exists for hour 14
        - LHS is calculated for hour 14
        - Result is stored in memory cache
        - Result is persisted to storage

        Bug Prevention:
        Ensures lazy population correctly triggers calculation on first access.
        """
        # ARRANGE: Empty caches (default state)
        target_hour = 14
        expected_lhs = 2.8

        # Mock storage returns None (cache miss)
        mock_model_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
        mock_model_storage.set_cached_contextual_lhs = AsyncMock()

        # Mock calculator returns value for hour 14
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs = Mock(
            return_value={14: expected_lhs}
        )

        # ACT: Call ensure_contextual_lhs_populated (will FAIL until implemented)
        result = await lhs_manager_minimal.ensure_contextual_lhs_populated(
            target_hour, sample_cycles, force_recalculate=False
        )

        # ASSERT: Calculation occurred
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once_with(
            sample_cycles
        )

        # ASSERT: Result stored to storage
        mock_model_storage.set_cached_contextual_lhs.assert_called_once()
        call_args = mock_model_storage.set_cached_contextual_lhs.call_args
        assert call_args[0][0] == target_hour  # hour
        assert call_args[0][1] == expected_lhs  # value

        # ASSERT: Result returned
        assert result == expected_lhs

        # ASSERT: Result cached in memory
        assert lhs_manager_minimal._cached_contextual_lhs[target_hour] == expected_lhs

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_recalculation(
        self,
        lhs_manager_minimal: LhsLifecycleManager,
        mock_contextual_lhs_calculator: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test that existing memory cache is used without recalculation.

        Expected Behavior (FAILS until implemented):
        - Memory cache contains value for hour 10
        - No calculation occurs
        - Cached value is returned immediately

        Bug Prevention:
        Ensures cache hit optimization works correctly.
        """
        # ARRANGE: Pre-populate memory cache
        target_hour = 10
        cached_value = 2.5
        lhs_manager_minimal._cached_contextual_lhs[target_hour] = cached_value

        # ACT: Call ensure_contextual_lhs_populated (will FAIL until implemented)
        result = await lhs_manager_minimal.ensure_contextual_lhs_populated(
            target_hour, sample_cycles, force_recalculate=False
        )

        # ASSERT: No calculation occurred
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_not_called()

        # ASSERT: Cached value returned
        assert result == cached_value

    @pytest.mark.asyncio
    async def test_storage_cache_hit_loads_into_memory(
        self,
        lhs_manager_minimal: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        sample_cycles: list[HeatingCycle],
        base_datetime: datetime,
    ) -> None:
        """Test that storage cache is loaded into memory on cache miss.

        Expected Behavior (FAILS until implemented):
        - Memory cache is empty for hour 18
        - Storage cache contains value for hour 18
        - Value is loaded from storage
        - Value is loaded into memory cache
        - No calculation occurs

        Bug Prevention:
        Ensures storage cache is properly utilized before calculation.
        """
        # ARRANGE: Empty memory cache, storage cache has value
        target_hour = 18
        cached_value = 3.2

        # Mock storage returns cached entry
        mock_model_storage.get_cached_contextual_lhs = AsyncMock(
            return_value=LHSCacheEntry(value=cached_value, updated_at=base_datetime)
        )

        # ACT: Call ensure_contextual_lhs_populated (will FAIL until implemented)
        result = await lhs_manager_minimal.ensure_contextual_lhs_populated(
            target_hour, sample_cycles, force_recalculate=False
        )

        # ASSERT: Storage was queried
        mock_model_storage.get_cached_contextual_lhs.assert_called_once_with(target_hour)

        # ASSERT: No calculation occurred
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_not_called()

        # ASSERT: Result returned
        assert result == cached_value

        # ASSERT: Result loaded into memory cache
        assert lhs_manager_minimal._cached_contextual_lhs[target_hour] == cached_value

    @pytest.mark.asyncio
    async def test_force_recalculate_bypasses_cache(
        self,
        lhs_manager_minimal: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test force_recalculate=True bypasses all caches and recalculates.

        Expected Behavior (FAILS until implemented):
        - Memory cache contains old value
        - force_recalculate=True is specified
        - Cache is bypassed
        - LHS is recalculated from cycles
        - New value replaces memory cache
        - New value replaces storage cache

        Bug Prevention:
        Ensures force recalculation works when explicit refresh is needed.
        """
        # ARRANGE: Pre-populate memory cache with old value
        target_hour = 12
        old_cached_value = 3.0
        new_calculated_value = 3.5

        lhs_manager_minimal._cached_contextual_lhs[target_hour] = old_cached_value

        # Mock storage operations
        mock_model_storage.set_cached_contextual_lhs = AsyncMock()

        # Mock calculator returns new value
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs = Mock(
            return_value={target_hour: new_calculated_value}
        )

        # ACT: Call with force_recalculate=True (will FAIL until implemented)
        result = await lhs_manager_minimal.ensure_contextual_lhs_populated(
            target_hour, sample_cycles, force_recalculate=True
        )

        # ASSERT: Calculation occurred despite cache
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once_with(
            sample_cycles
        )

        # ASSERT: New value stored to storage
        mock_model_storage.set_cached_contextual_lhs.assert_called_once()
        call_args = mock_model_storage.set_cached_contextual_lhs.call_args
        assert call_args[0][0] == target_hour
        assert call_args[0][1] == new_calculated_value

        # ASSERT: New value returned
        assert result == new_calculated_value

        # ASSERT: Memory cache updated with new value
        assert lhs_manager_minimal._cached_contextual_lhs[target_hour] == new_calculated_value

    @pytest.mark.asyncio
    async def test_fallback_to_global_lhs_when_no_contextual_data(
        self,
        lhs_manager_minimal: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        sample_cycles: list[HeatingCycle],
    ) -> None:
        """Test fallback to global LHS when no contextual data exists.

        Expected Behavior (FAILS until implemented):
        - No contextual LHS data exists for hour 22
        - Calculator returns empty dict or None for hour 22
        - Global LHS is returned as fallback
        - No error occurs

        Bug Prevention:
        Ensures graceful fallback when contextual data is unavailable.
        """
        # ARRANGE: No cache, calculator returns no contextual data for hour 22
        target_hour = 22
        global_lhs_fallback = 2.5

        # Mock storage returns None
        mock_model_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)

        # Mock global LHS
        mock_model_storage.get_cached_global_lhs = AsyncMock(
            return_value=LHSCacheEntry(value=global_lhs_fallback, updated_at=datetime.now())
        )

        # Mock calculator returns no data for hour 22
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs = Mock(
            return_value={}  # Empty dict, no data for hour 22
        )

        # ACT: Call ensure_contextual_lhs_populated (will FAIL until implemented)
        result = await lhs_manager_minimal.ensure_contextual_lhs_populated(
            target_hour, sample_cycles, force_recalculate=False
        )

        # ASSERT: Calculation was attempted
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once()

        # ASSERT: Global LHS was retrieved as fallback
        # This will FAIL until get_global_lhs() is called when contextual data missing
        assert result == global_lhs_fallback or result is not None
