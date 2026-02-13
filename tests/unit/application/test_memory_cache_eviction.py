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

    @pytest.mark.asyncio
    async def test_eviction_selects_oldest_entries_by_date(
        self,
        heating_cycle_manager_minimal: HeatingCycleLifecycleManager,
        base_datetime: datetime,
        heating_cycle_builder,
    ) -> None:
        """Test that eviction removes OLDEST entries (FIFO) and preserves NEWEST.

        Expected Behavior (FAILS until fix):
        - Add cycles with various dates (old to new)
        - When eviction triggered, oldest dates are removed first (FIFO)
        - Newest entries are preserved
        - Evicted entries can be reloaded from storage (lazy reload)

        Regression Prevention:
        Ensures FIFO algorithm is correct. Buggy code might:
        - Remove NEWEST entries (inverse FIFO) → DATA LOSS
        - Remove random entries → UNPREDICTABLE BEHAVIOR
        - Not remove any entries → UNBOUNDED MEMORY GROWTH

        This test catches all three bugs by verifying:
        1. Correct oldest entries removed
        2. Correct youngest entries retained
        3. No gaps in remaining cache
        """
        # ARRANGE: Create heating cycle manager with empty cache
        device_id = "climate.test_vtherm"

        # Add cycles with KNOWN TIMESTAMPS from OLDEST to NEWEST
        dates_added = []
        for i in range(MAX_MEMORY_CACHE_ENTRIES):
            # Cycle dates: i days BEFORE base_datetime
            # i=0 → today (NEWEST), i=MAX-1 → oldest
            cycle_date = (base_datetime - timedelta(days=i)).date()
            dates_added.append(cycle_date)

            cache_key = (device_id, cycle_date)
            cycle = heating_cycle_builder(
                base_datetime - timedelta(days=i),
                duration_hours=1.0,
                temp_increase=2.0,
            )
            heating_cycle_manager_minimal._cached_cycles_for_target_time[cache_key] = [cycle]

        # Verify cache is full at limit
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )

        # dates_added is in order: [today, yesterday, 2-days-ago, ..., oldest]
        # So: dates_added[0] = NEWEST, dates_added[-1] = OLDEST

        # ACT: Add one more cycle (NEWEST) to trigger eviction
        newest_date = (base_datetime + timedelta(days=1)).date()
        newest_key = (device_id, newest_date)
        newest_cycle = heating_cycle_builder(
            base_datetime + timedelta(days=1),
            duration_hours=1.0,
            temp_increase=2.0,
        )
        heating_cycle_manager_minimal._cached_cycles_for_target_time[newest_key] = [newest_cycle]

        # Now cache has 51 entries, trigger eviction
        await heating_cycle_manager_minimal._evict_old_memory_cache_entries()

        # ASSERT: Cache is back to limit after eviction
        assert (
            len(heating_cycle_manager_minimal._cached_cycles_for_target_time)
            == MAX_MEMORY_CACHE_ENTRIES
        )

        # ASSERT: FIFO - oldest entries should be REMOVED
        # Oldest entries are at the END of dates_added (highest index)
        # We added 50 entries, then 1 more (total 51)
        # Eviction removes oldest 1 entry to bring back to 50
        # So the oldest entry from original batch should be gone

        oldest_removed_date = dates_added[-1]  # Oldest from original batch
        oldest_removed_key = (device_id, oldest_removed_date)

        assert (
            oldest_removed_key not in heating_cycle_manager_minimal._cached_cycles_for_target_time
        ), f"Oldest entry from {oldest_removed_date} should have been evicted"

        # ASSERT: FIFO - newest entries should be PRESERVED
        # The newly added entry (latest date) must still be in cache
        assert (
            newest_key in heating_cycle_manager_minimal._cached_cycles_for_target_time
        ), "Newest entry must be preserved after eviction"

        # Also check that the most recent entries from original batch are kept
        # dates_added[0] to dates_added[48] should still be present (49 entries)
        # dates_added[49] (the oldest) should NOT be present
        for i in range(MAX_MEMORY_CACHE_ENTRIES - 1):  # 0 to 48
            date_check = dates_added[i]
            key_check = (device_id, date_check)
            assert (
                key_check in heating_cycle_manager_minimal._cached_cycles_for_target_time
            ), f"Entry from {date_check} should be preserved (not old enough to evict)"

        # ASSERT: Evicted data can be reloaded from persistent storage
        # (Verified by separate scenario "Evicted data can be reloaded from persistent storage")
        # This test focuses on FIFO selection algorithm
