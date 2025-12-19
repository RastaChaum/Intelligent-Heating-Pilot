"""Tests for HACycleCache adapter."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CycleCacheData,
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.cycle_cache import (
    HACycleCache,
    DEFAULT_RETENTION_DAYS,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def entry_id() -> str:
    """Create a test entry ID."""
    return "test_entry_123"


@pytest.fixture
def device_id() -> str:
    """Create a test device ID."""
    return "climate.test_vtherm"


@pytest.fixture
def base_time() -> datetime:
    """Create a base time for tests."""
    return datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_store() -> Mock:
    """Create a mock Store."""
    store_mock = Mock()
    store_mock.async_load = AsyncMock(return_value=None)
    store_mock.async_save = AsyncMock()
    return store_mock


@pytest.fixture
async def cache(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HACycleCache:
    """Create cache adapter with mocked dependencies."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.cycle_cache.Store",
        return_value=mock_store,
    ):
        cache_obj = HACycleCache(mock_hass, entry_id)
        await cache_obj._ensure_loaded()
        return cache_obj


def create_cycle(
    device_id: str,
    start_time: datetime,
    duration_hours: float = 1.0,
    temp_increase: float = 2.0,
) -> HeatingCycle:
    """Helper to create a heating cycle."""
    end_time = start_time + timedelta(hours=duration_hours)
    start_temp = 18.0
    end_temp = start_temp + temp_increase
    target_temp = end_temp + 0.5
    
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=target_temp,
        end_temp=end_temp,
        start_temp=start_temp,
        tariff_details=None,
    )


def test_init(mock_hass: Mock, entry_id: str) -> None:
    """Test cache adapter initialization."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.cycle_cache.Store"
    ) as mock_store_class:
        cache = HACycleCache(mock_hass, entry_id, retention_days=45)
        
        assert cache._hass == mock_hass
        assert cache._entry_id == entry_id
        assert cache._retention_days == 45
        mock_store_class.assert_called_once()


@pytest.mark.asyncio
async def test_get_cache_data_no_cache(cache: HACycleCache, device_id: str) -> None:
    """Test getting cache data when no cache exists."""
    result = await cache.get_cache_data(device_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_cache_data_with_stored_data(
    mock_hass: Mock,
    entry_id: str,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test getting cache data with stored cycles."""
    # Setup stored data
    stored_data = {
        device_id: {
            "cycles": [
                {
                    "device_id": device_id,
                    "start_time": base_time.isoformat(),
                    "end_time": (base_time + timedelta(hours=1)).isoformat(),
                    "target_temp": 20.5,
                    "end_temp": 20.0,
                    "start_temp": 18.0,
                    "tariff_details": None,
                }
            ],
            "last_search_time": (base_time + timedelta(hours=2)).isoformat(),
            "retention_days": 30,
        }
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.cycle_cache.Store",
        return_value=mock_store,
    ):
        cache = HACycleCache(mock_hass, entry_id)
        result = await cache.get_cache_data(device_id)
        
        assert result is not None
        assert result.device_id == device_id
        assert result.cycle_count == 1
        assert result.retention_days == 30


@pytest.mark.asyncio
async def test_append_cycles_to_empty_cache(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test appending cycles to empty cache."""
    cycles = [
        create_cycle(device_id, base_time),
        create_cycle(device_id, base_time + timedelta(hours=2)),
    ]
    search_end = base_time + timedelta(hours=4)
    
    await cache.append_cycles(device_id, cycles, search_end)
    
    # Verify save was called
    mock_store.async_save.assert_called_once()
    
    # Verify data structure
    assert device_id in cache._data
    assert len(cache._data[device_id]["cycles"]) == 2
    assert cache._data[device_id]["last_search_time"] == search_end.isoformat()


@pytest.mark.asyncio
async def test_append_cycles_to_existing_cache(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test appending cycles to existing cache."""
    # First append
    initial_cycles = [create_cycle(device_id, base_time)]
    await cache.append_cycles(device_id, initial_cycles, base_time + timedelta(hours=1))
    
    # Reset mock to track second append
    mock_store.async_save.reset_mock()
    
    # Second append with new cycles
    new_cycles = [
        create_cycle(device_id, base_time + timedelta(hours=2)),
        create_cycle(device_id, base_time + timedelta(hours=4)),
    ]
    search_end = base_time + timedelta(hours=6)
    
    await cache.append_cycles(device_id, new_cycles, search_end)
    
    # Verify save was called
    mock_store.async_save.assert_called_once()
    
    # Verify combined data
    assert len(cache._data[device_id]["cycles"]) == 3
    assert cache._data[device_id]["last_search_time"] == search_end.isoformat()


@pytest.mark.asyncio
async def test_append_cycles_deduplication(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test that duplicate cycles are not added."""
    # First append
    cycle1 = create_cycle(device_id, base_time)
    await cache.append_cycles(device_id, [cycle1], base_time + timedelta(hours=1))
    
    # Second append with same cycle (duplicate)
    cycle1_dup = create_cycle(device_id, base_time)
    await cache.append_cycles(device_id, [cycle1_dup], base_time + timedelta(hours=2))
    
    # Should still have only 1 cycle
    assert len(cache._data[device_id]["cycles"]) == 1


@pytest.mark.asyncio
async def test_append_cycles_with_empty_list(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test appending empty list (period with no cycles)."""
    search_end = base_time + timedelta(hours=1)
    
    await cache.append_cycles(device_id, [], search_end)
    
    # Should still update last_search_time
    mock_store.async_save.assert_called_once()
    assert cache._data[device_id]["last_search_time"] == search_end.isoformat()
    assert len(cache._data[device_id]["cycles"]) == 0


@pytest.mark.asyncio
async def test_prune_old_cycles(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test pruning cycles older than retention period."""
    # Create cycles at different times
    cycles = [
        create_cycle(device_id, base_time - timedelta(days=35)),  # Too old
        create_cycle(device_id, base_time - timedelta(days=20)),  # Within retention
        create_cycle(device_id, base_time - timedelta(days=10)),  # Within retention
        create_cycle(device_id, base_time),  # Recent
    ]
    
    await cache.append_cycles(device_id, cycles, base_time)
    
    # Reset mock to track prune operation
    mock_store.async_save.reset_mock()
    
    # Prune old cycles
    await cache.prune_old_cycles(device_id, base_time)
    
    # Should have removed 1 cycle (35 days old)
    mock_store.async_save.assert_called_once()
    assert len(cache._data[device_id]["cycles"]) == 3


@pytest.mark.asyncio
async def test_prune_old_cycles_no_cache(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test pruning when no cache exists."""
    await cache.prune_old_cycles(device_id, base_time)
    
    # Should not save anything
    mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_prune_old_cycles_nothing_to_prune(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test pruning when all cycles are recent."""
    cycles = [
        create_cycle(device_id, base_time - timedelta(days=5)),
        create_cycle(device_id, base_time),
    ]
    
    await cache.append_cycles(device_id, cycles, base_time)
    
    # Reset mock to track prune operation
    mock_store.async_save.reset_mock()
    
    await cache.prune_old_cycles(device_id, base_time)
    
    # Should not save (nothing changed)
    mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_clear_cache(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test clearing cache for a device."""
    # Add some data
    cycles = [create_cycle(device_id, base_time)]
    await cache.append_cycles(device_id, cycles, base_time)
    
    # Reset mock to track clear operation
    mock_store.async_save.reset_mock()
    
    # Clear cache
    await cache.clear_cache(device_id)
    
    # Should have removed device data
    mock_store.async_save.assert_called_once()
    assert device_id not in cache._data


@pytest.mark.asyncio
async def test_clear_cache_no_data(
    cache: HACycleCache,
    device_id: str,
    mock_store: Mock,
) -> None:
    """Test clearing cache when no data exists."""
    await cache.clear_cache(device_id)
    
    # Should not save (nothing to clear)
    mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_get_last_search_time(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
) -> None:
    """Test getting last search time."""
    search_time = base_time + timedelta(hours=2)
    
    await cache.append_cycles(device_id, [], search_time)
    
    result = await cache.get_last_search_time(device_id)
    
    assert result == search_time


@pytest.mark.asyncio
async def test_get_last_search_time_no_cache(
    cache: HACycleCache,
    device_id: str,
) -> None:
    """Test getting last search time when no cache exists."""
    result = await cache.get_last_search_time(device_id)
    
    assert result is None


@pytest.mark.asyncio
async def test_serialization_roundtrip(
    cache: HACycleCache,
    device_id: str,
    base_time: datetime,
) -> None:
    """Test that cycles can be serialized and deserialized correctly."""
    original_cycles = [
        create_cycle(device_id, base_time),
        create_cycle(device_id, base_time + timedelta(hours=2)),
    ]
    
    await cache.append_cycles(device_id, original_cycles, base_time + timedelta(hours=3))
    
    # Retrieve and verify
    cache_data = await cache.get_cache_data(device_id)
    
    assert cache_data is not None
    assert len(cache_data.cycles) == 2
    assert cache_data.cycles[0].device_id == device_id
    assert cache_data.cycles[0].start_time == base_time
