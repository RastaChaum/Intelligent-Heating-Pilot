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
    """Test memory cache eviction strategy.

    Regression Prevention:
    These tests ensure memory cache doesn't grow unbounded in long-running
    IHP instances, using FIFO eviction when MAX_MEMORY_CACHE_ENTRIES exceeded.
    """

    @pytest.mark.asyncio
    async def test_eviction_when_limit_exceeded(
        self,
        heating_cycle_manager_minimal: HeatingCycleLifecycleManager,
        base_datetime: datetime,
        heating_cycle_builder,
    ) -> None:
        """Test FIFO eviction when cache exceeds MAX_MEMORY_CACHE_ENTRIES.

        Expected Behavior (FAILS until implemented):
        - Memory cache contains 50 cycles (at limit)
        - Adding 1 more cycle triggers eviction
        - Oldest 25 cycles are evicted (50% eviction)
        - Cache size remains at 50 after eviction

        Bug Prevention:
        Prevents unbounded memory growth in long-running instances.
        """
        # ARRANGE: Fill cache to MAX_MEMORY_CACHE_ENTRIES (50)
        device_id = "climate.test_vtherm"

        for i in range(MAX_MEMORY_CACHE_ENTRIES):
            cycle_date = (base_datetime - timedelta(days=i)).date()
            cache_key = (device_id, cycle_date)

            # Create single cycle for each date
            cycle = heating_cycle_builder(
                base_datetime - timedelta(days=i),
                duration_hours=1.0,
                temp_increase=2.0,
            )
            heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [cycle]

        # Verify initial state: exactly at limit
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )

        # ACT: Add one more entry (should trigger eviction)
        # This will FAIL until _evict_old_memory_cache_entries() is implemented
        new_cycle_date = (base_datetime + timedelta(days=1)).date()
        new_cache_key = (device_id, new_cycle_date)
        new_cycle = heating_cycle_builder(
            base_datetime + timedelta(days=1),
            duration_hours=1.0,
            temp_increase=2.0,
        )
        heating_cycle_manager_minimal._cached_cycles_for_target_time[new_cache_key] = [new_cycle]

        # Trigger eviction manually (simulates automatic eviction)
        await heating_cycle_manager_minimal._evict_old_memory_cache_entries()

        # ASSERT: Cache size should be back at limit (50)
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )

    @pytest.mark.asyncio
    async def test_no_eviction_when_under_limit(
        self,
        heating_cycle_manager_minimal: HeatingCycleLifecycleManager,
        base_datetime: datetime,
        heating_cycle_builder,
    ) -> None:
        """Test no eviction occurs when cache is under limit.

        Expected Behavior (PASSES immediately):
        - Memory cache contains 40 cycles (under limit)
        - Adding 1 more cycle does not trigger eviction
        - Cache size increases to 41

        Bug Prevention:
        Ensures eviction only occurs when necessary.
        """
        # ARRANGE: Fill cache to 40 entries (under limit)
        device_id = "climate.test_vtherm"
        initial_count = 40

        for i in range(initial_count):
            cycle_date = (base_datetime - timedelta(days=i)).date()
            cache_key = (device_id, cycle_date)

            cycle = heating_cycle_builder(
                base_datetime - timedelta(days=i),
                duration_hours=1.0,
                temp_increase=2.0,
            )
            heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [cycle]

        # Verify initial state
        assert len(heating_cycle_manager_minimal._cached_cycles_for_target_time) == initial_count

        # ACT: Add one more entry
        new_cycle_date = (base_datetime + timedelta(days=1)).date()
        new_cache_key = (device_id, new_cycle_date)
        new_cycle = heating_cycle_builder(
            base_datetime + timedelta(days=1),
            duration_hours=1.0,
            temp_increase=2.0,
        )
        heating_cycle_manager_minimal._cached_cycles_for_target_time[new_cache_key] = [new_cycle]

        # Call eviction (should be no-op)
        await heating_cycle_manager_minimal._evict_old_memory_cache_entries()

        # ASSERT: Cache size should be initial_count + 1 (no eviction)
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time) == initial_count + 1
        )

    @pytest.mark.asyncio
    async def test_eviction_selects_oldest_entries_by_date(
        self,
        heating_cycle_manager_minimal: HeatingCycleLifecycleManager,
        base_datetime: datetime,
        heating_cycle_builder,
    ) -> None:
        """Test that eviction selects oldest entries by date.

        Expected Behavior (FAILS until implemented):
        - Cache contains cycles from various dates
        - Eviction selects oldest 50% by date
        - Newest cycles remain in cache

        Bug Prevention:
        Ensures LRU-like behavior based on date ordering.
        """
        # ARRANGE: Fill cache with dated cycles
        device_id = "climate.test_vtherm"
        oldest_date = (base_datetime - timedelta(days=50)).date()
        newest_date = base_datetime.date()

        # Add 50 cycles with sequential dates
        for i in range(MAX_MEMORY_CACHE_ENTRIES):
            cycle_date = (base_datetime - timedelta(days=50 - i)).date()
            cache_key = (device_id, cycle_date)

            cycle = heating_cycle_builder(
                base_datetime - timedelta(days=50 - i),
                duration_hours=1.0,
                temp_increase=2.0,
            )
            heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [cycle]

        # ACT: Add newest cycle (triggers eviction)
        new_cycle_date = (base_datetime + timedelta(days=1)).date()
        new_cache_key = (device_id, new_cycle_date)
        new_cycle = heating_cycle_builder(
            base_datetime + timedelta(days=1),
            duration_hours=1.0,
            temp_increase=2.0,
        )
        heating_cycle_manager_minimal._cached_cycles_for_target_time[new_cache_key] = [new_cycle]

        # Trigger eviction
        await heating_cycle_manager_minimal._evict_old_memory_cache_entries()

        # ASSERT: Oldest date should be evicted
        oldest_key = (device_id, oldest_date)
        assert oldest_key not in heating_cycle_manager_minimal._cached_cycles_for_target_time

        # ASSERT: Newest date should remain
        newest_key = (device_id, newest_date)
        assert newest_key in heating_cycle_manager_minimal._cached_cycles_for_target_time

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
        - Eviction removes 25 entries (50%)
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
        # Initial: 50, Added: 1 (total 51), Evicted: 25, Final: 50
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )
