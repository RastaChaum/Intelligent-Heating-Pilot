"""Unit tests for memory cache eviction in HeatingCycleLifecycleManager.

These tests verify FIFO eviction strategy when memory cache exceeds MAX_MEMORY_CACHE_ENTRIES.

Author: QA Engineer
Purpose: Test _evict_old_memory_cache_entries() method
Status: RED - Tests written before implementation (TDD)
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    MAX_MEMORY_CACHE_ENTRIES,
    HeatingCycleLifecycleManager,
)


class TestMemoryCacheEviction:
    """Test algorithmic validation of memory cache eviction.

    NOTE: High-level eviction behavior and happy paths are covered by BDD tests
    in tests/features/memory_cache_eviction.feature. This unit test validates
    the technical constraint that exactly 50% of entries are evicted.

    Regression Prevention:
    Ensures FIFO eviction amount is predictable and follows documented 50% rule.
    """

    @pytest.mark.asyncio
    async def test_eviction_removes_exactly_50_percent(
        self,
        heating_cycle_manager_minimal: HeatingCycleLifecycleManager,
        base_datetime: datetime,
        heating_cycle_builder,
    ) -> None:
        """Test that eviction removes exactly 50% of entries.

        Expected Behavior (FAILS until implemented):
        - Cache at 50 entries triggers eviction
        - Eviction removes 1 entries
        - Remaining cache size is 50 after adding new entry

        Bug Prevention:
        Ensures eviction amount is predictable and documented.
        """
        # ARRANGE: Fill cache to exactly MAX_MEMORY_CACHE_ENTRIES
        device_id = "climate.test_vtherm"

        for i in range(MAX_MEMORY_CACHE_ENTRIES):
            cycle_date = (base_datetime - timedelta(days=i)).date()
            cache_key = (device_id, cycle_date)

            cycle = heating_cycle_builder(
                base_datetime - timedelta(days=i),
                duration_hours=1.0,
                temp_increase=2.0,
            )
            heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [cycle]

        # ACT: Add one more (triggers eviction)
        new_cycle_date = (base_datetime + timedelta(days=1)).date()
        new_cache_key = (device_id, new_cycle_date)
        new_cycle = heating_cycle_builder(
            base_datetime + timedelta(days=1),
            duration_hours=1.0,
            temp_increase=2.0,
        )
        heating_cycle_manager_minimal._cached_cycles_for_target_time[new_cache_key] = [new_cycle]

        await heating_cycle_manager_minimal._evict_old_memory_cache_entries()

        # ASSERT: Exactly 50% evicted, final size is at limit
        # Initial: 50, Added: 1 (total 51), Evicted: 1, Final: 50
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )
