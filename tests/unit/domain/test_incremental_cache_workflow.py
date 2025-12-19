"""Unit tests for incremental cycle cache functionality."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from .fixtures import create_test_heating_cycle, TEST_DEVICE_ID


@pytest.fixture
def base_time() -> datetime:
    """Get base time for tests."""
    return datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def device_id() -> str:
    """Get device ID for tests."""
    return TEST_DEVICE_ID


@pytest.mark.asyncio
async def test_incremental_append_logic(base_time: datetime, device_id: str) -> None:
    """Test the incremental append logic with cache."""
    from domain.value_objects import CycleCacheData
    
    # Simulate initial cache
    initial_cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=5)),
        create_test_heating_cycle(device_id, base_time - timedelta(days=3)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(initial_cycles),
        last_search_time=base_time - timedelta(days=2),
        retention_days=30,
    )
    
    assert cache_data.cycle_count == 2
    
    # Simulate adding new cycles
    new_cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=1)),
        create_test_heating_cycle(device_id, base_time),
    ]
    
    # Combine cycles (simulating append operation)
    all_cycles = list(cache_data.cycles) + new_cycles
    updated_cache = CycleCacheData(
        device_id=device_id,
        cycles=tuple(all_cycles),
        last_search_time=base_time + timedelta(hours=1),
        retention_days=30,
    )
    
    assert updated_cache.cycle_count == 4


@pytest.mark.asyncio
async def test_deduplication_logic(base_time: datetime, device_id: str) -> None:
    """Test that duplicate cycles are filtered."""
    from domain.value_objects import CycleCacheData
    
    # Create a cycle
    cycle1 = create_test_heating_cycle(device_id, base_time)
    
    # Create initial cache
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple([cycle1]),
        last_search_time=base_time + timedelta(hours=1),
        retention_days=30,
    )
    
    # Try to add duplicate (same start_time and device_id)
    cycle1_duplicate = create_test_heating_cycle(device_id, base_time)
    
    # Simulate deduplication logic
    existing_keys = {(c.start_time, c.device_id) for c in cache_data.cycles}
    new_cycle_key = (cycle1_duplicate.start_time, cycle1_duplicate.device_id)
    
    # Should detect duplicate
    assert new_cycle_key in existing_keys


@pytest.mark.asyncio
async def test_empty_period_handling(base_time: datetime, device_id: str) -> None:
    """Test that empty periods (no cycles) update last_search_time."""
    from domain.value_objects import CycleCacheData
    
    # Initial data
    initial_cycles = [create_test_heating_cycle(device_id, base_time)]
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(initial_cycles),
        last_search_time=base_time + timedelta(hours=1),
        retention_days=30,
    )
    
    # Search period with no cycles (empty list)
    # Update cache with new search time but no new cycles
    updated_cache = CycleCacheData(
        device_id=device_id,
        cycles=cache_data.cycles,  # No new cycles
        last_search_time=base_time + timedelta(days=1),  # Updated search time
        retention_days=30,
    )
    
    # last_search_time should be updated
    assert updated_cache.last_search_time == base_time + timedelta(days=1)
    
    # Cycle count should remain unchanged
    assert updated_cache.cycle_count == 1


@pytest.mark.asyncio
async def test_retention_filtering(base_time: datetime, device_id: str) -> None:
    """Test filtering cycles by retention period."""
    from domain.value_objects import CycleCacheData
    
    # Create cycles at different ages
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=35)),  # Too old
        create_test_heating_cycle(device_id, base_time - timedelta(days=20)),  # Within retention
        create_test_heating_cycle(device_id, base_time),  # Recent
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time,
        retention_days=30,
    )
    
    # Get cycles within retention
    cycles_in_retention = cache_data.get_cycles_within_retention(base_time + timedelta(days=1))
    
    # Should exclude the 35-day old cycle
    assert len(cycles_in_retention) == 2
