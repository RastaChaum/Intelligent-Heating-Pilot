"""Tests for HAHeatingCycleStorage adapter (formerly HACycleCache).

This adapter implements IHeatingCycleStorage by using Home Assistant's storage helper
to persist heating cycles with incremental update support.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle

# This import will change from HACycleCache to HAHeatingCycleStorage after refactoring
try:
    from custom_components.intelligent_heating_pilot.infrastructure.adapters.heating_cycle_storage import (
        HAHeatingCycleStorage,
    )

    HEATING_CYCLE_STORAGE_AVAILABLE = True
except ImportError:
    # Fallback during migration - use old names
    try:
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.cycle_cache import (
            HACycleCache as HAHeatingCycleStorage,
        )

        HEATING_CYCLE_STORAGE_AVAILABLE = True
    except ImportError:
        HEATING_CYCLE_STORAGE_AVAILABLE = False
        HAHeatingCycleStorage = None  # type: ignore


def _get_storage_patch_path() -> str:
    """Helper to get the correct patch path for storage module.

    Returns path to base_ha_storage.Store where Store is actually imported.
    After refactoring, Store is imported in base_ha_storage, not in individual storage files.
    """
    return (
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
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
async def cache(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HAHeatingCycleStorage:
    """Create cache adapter with mocked dependencies."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        cache_obj = HAHeatingCycleStorage(mock_hass, entry_id)
        await cache_obj._ensure_loaded()
        return cache_obj


def create_test_heating_cycle(
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


pytestmark = pytest.mark.skipif(
    not HEATING_CYCLE_STORAGE_AVAILABLE,
    reason="HAHeatingCycleStorage not yet available (migration in progress)",
)


class TestHAHeatingCycleStorageInheritance:
    """Test that HAHeatingCycleStorage correctly inherits from BaseHAStorageAdapter.

    These tests verify the refactoring: HAHeatingCycleStorage should extend
    BaseHAStorageAdapter and use its common functionality.
    """

    def test_inherits_from_base_storage_adapter(self) -> None:
        """Verify HAHeatingCycleStorage extends BaseHAStorageAdapter.

        This test will FAIL until refactoring is complete.
        """
        try:
            from custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage import (
                BaseHAStorageAdapter,
            )

            assert issubclass(HAHeatingCycleStorage, BaseHAStorageAdapter)
        except ImportError:
            pytest.skip("BaseHAStorageAdapter not yet implemented")

    def test_implements_heating_cycle_storage_interface(self) -> None:
        """Verify HAHeatingCycleStorage implements IHeatingCycleStorage interface."""
        try:
            from custom_components.intelligent_heating_pilot.domain.interfaces.heating_cycle_storage_interface import (
                IHeatingCycleStorage,
            )

            assert issubclass(HAHeatingCycleStorage, IHeatingCycleStorage)
        except ImportError:
            # Fallback to old interface name
            from custom_components.intelligent_heating_pilot.domain.interfaces.cycle_cache_interface import (
                IHeatingCycleStorage,
            )

            assert issubclass(HAHeatingCycleStorage, IHeatingCycleStorage)

    @pytest.mark.asyncio
    async def test_uses_base_class_parse_datetime(self, mock_hass: Mock, entry_id: str) -> None:
        """Verify that datetime parsing uses base class method.

        This test will FAIL until BaseHAStorageAdapter is implemented.
        """
        try:
            patch_path = _get_storage_patch_path()
        except ImportError:
            pytest.skip("BaseHAStorageAdapter not yet implemented")
            return

        with patch(patch_path):
            storage = HAHeatingCycleStorage(mock_hass, entry_id)

            # Verify the method exists and works
            result = storage._parse_datetime("2025-12-18T14:30:00+00:00")
            assert result.year == 2025
            assert result.month == 12
            assert result.day == 18

    @pytest.mark.asyncio
    async def test_uses_base_class_ensure_loaded(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Verify that _ensure_loaded uses base class implementation.

        This test verifies the lazy loading behavior is inherited correctly.
        """
        patch_path = _get_storage_patch_path()

        with patch(patch_path, return_value=mock_store):
            storage = HAHeatingCycleStorage(mock_hass, entry_id)

            # Should not be loaded yet
            assert storage._loaded is False

            # First call should load
            await storage._ensure_loaded()
            assert storage._loaded is True
            assert mock_store.async_load.call_count == 1

            # Second call should use cache
            await storage._ensure_loaded()
            assert mock_store.async_load.call_count == 1  # Still 1, not 2


def test_init(mock_hass: Mock, entry_id: str) -> None:
    """Test cache adapter initialization."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path) as mock_store_class:
        cache = HAHeatingCycleStorage(mock_hass, entry_id, retention_days=45)

        assert cache._hass == mock_hass
        assert cache._entry_id == entry_id
        assert cache._retention_days == 45
        mock_store_class.assert_called_once()


@pytest.mark.asyncio
async def test_get_cache_data_no_cache(cache: HAHeatingCycleStorage, device_id: str) -> None:
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

    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        cache = HAHeatingCycleStorage(mock_hass, entry_id)
        result = await cache.get_cache_data(device_id)

        assert result is not None
        assert result.device_id == device_id
        assert result.cycle_count == 1
        assert result.retention_days == 30


@pytest.mark.asyncio
async def test_append_cycles_to_empty_cache(
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test appending cycles to empty cache."""
    cycles = [
        create_test_heating_cycle(device_id, base_time),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
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
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test appending cycles to existing cache."""
    # First append
    initial_cycles = [create_test_heating_cycle(device_id, base_time)]
    await cache.append_cycles(device_id, initial_cycles, base_time + timedelta(hours=1))

    # Reset mock to track second append
    mock_store.async_save.reset_mock()

    # Second append with new cycles
    new_cycles = [
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=4)),
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
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test that duplicate cycles are not added."""
    # First append
    cycle1 = create_test_heating_cycle(device_id, base_time)
    await cache.append_cycles(device_id, [cycle1], base_time + timedelta(hours=1))

    # Second append with same cycle (duplicate)
    cycle1_dup = create_test_heating_cycle(device_id, base_time)
    await cache.append_cycles(device_id, [cycle1_dup], base_time + timedelta(hours=2))

    # Should still have only 1 cycle
    assert len(cache._data[device_id]["cycles"]) == 1


@pytest.mark.asyncio
async def test_append_cycles_with_empty_list(
    cache: HAHeatingCycleStorage,
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
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test pruning cycles older than retention period."""
    # Create cycles at different times
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=35)),  # Too old
        create_test_heating_cycle(device_id, base_time - timedelta(days=20)),  # Within retention
        create_test_heating_cycle(device_id, base_time - timedelta(days=10)),  # Within retention
        create_test_heating_cycle(device_id, base_time),  # Recent
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
    cache: HAHeatingCycleStorage,
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
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test pruning when all cycles are recent."""
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=5)),
        create_test_heating_cycle(device_id, base_time),
    ]

    await cache.append_cycles(device_id, cycles, base_time)

    # Reset mock to track prune operation
    mock_store.async_save.reset_mock()

    await cache.prune_old_cycles(device_id, base_time)

    # Should not save (nothing changed)
    mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_clear_cache(
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
    mock_store: Mock,
) -> None:
    """Test clearing cache for a device."""
    # Add some data
    cycles = [create_test_heating_cycle(device_id, base_time)]
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
    cache: HAHeatingCycleStorage,
    device_id: str,
    mock_store: Mock,
) -> None:
    """Test clearing cache when no data exists."""
    await cache.clear_cache(device_id)

    # Should not save (nothing to clear)
    mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_get_last_search_time(
    cache: HAHeatingCycleStorage,
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
    cache: HAHeatingCycleStorage,
    device_id: str,
) -> None:
    """Test getting last search time when no cache exists."""
    result = await cache.get_last_search_time(device_id)

    assert result is None


@pytest.mark.asyncio
async def test_serialization_roundtrip(
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
) -> None:
    """Test that cycles can be serialized and deserialized correctly."""
    original_cycles = [
        create_test_heating_cycle(device_id, base_time),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
    ]

    await cache.append_cycles(device_id, original_cycles, base_time + timedelta(hours=3))

    # Retrieve and verify
    cache_data = await cache.get_cache_data(device_id)

    assert cache_data is not None
    assert len(cache_data.cycles) == 2
    assert cache_data.cycles[0].device_id == device_id
    assert cache_data.cycles[0].start_time == base_time


@pytest.mark.asyncio
async def test_dead_time_cycle_minutes_serialization(
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
) -> None:
    """Test that dead_time_cycle_minutes is correctly persisted and restored.

    This regression test ensures the dead_time_cycle_minutes field is included
    in serialization/deserialization, which is critical for accurate slope calculations.
    """
    # Create cycle with dead_time_cycle_minutes
    cycle_with_deadtime = HeatingCycle(
        device_id=device_id,
        start_time=base_time,
        end_time=base_time + timedelta(hours=1),
        target_temp=22.5,
        end_temp=21.5,
        start_temp=19.0,
        tariff_details=None,
        dead_time_cycle_minutes=14.5,  # Explicit dead time
    )

    # Persist the cycle
    await cache.append_cycles(device_id, [cycle_with_deadtime], base_time + timedelta(hours=2))

    # Retrieve and verify dead_time_cycle_minutes is preserved
    cache_data = await cache.get_cache_data(device_id)

    assert cache_data is not None
    assert len(cache_data.cycles) == 1
    retrieved_cycle = cache_data.cycles[0]

    # Verify all fields including dead_time_cycle_minutes
    assert retrieved_cycle.device_id == device_id
    assert retrieved_cycle.start_time == base_time
    assert retrieved_cycle.end_time == base_time + timedelta(hours=1)
    assert retrieved_cycle.target_temp == 22.5
    assert retrieved_cycle.end_temp == 21.5
    assert retrieved_cycle.start_temp == 19.0
    assert retrieved_cycle.dead_time_cycle_minutes == 14.5  # CRITICAL: must be preserved


@pytest.mark.asyncio
async def test_dead_time_cycle_minutes_none_serialization(
    cache: HAHeatingCycleStorage,
    device_id: str,
    base_time: datetime,
) -> None:
    """Test that dead_time_cycle_minutes=None is correctly handled.

    Some cycles may not have dead time calculated (e.g., insufficient data).
    Ensure None values are properly serialized/deserialized.
    """
    # Create cycle without dead_time_cycle_minutes (defaults to None)
    cycle_without_deadtime = HeatingCycle(
        device_id=device_id,
        start_time=base_time,
        end_time=base_time + timedelta(hours=1),
        target_temp=20.0,
        end_temp=19.5,
        start_temp=18.0,
        tariff_details=None,
        dead_time_cycle_minutes=None,
    )

    # Persist
    await cache.append_cycles(device_id, [cycle_without_deadtime], base_time + timedelta(hours=2))

    # Retrieve and verify
    cache_data = await cache.get_cache_data(device_id)

    assert cache_data is not None
    assert len(cache_data.cycles) == 1
    retrieved_cycle = cache_data.cycles[0]

    # Verify dead_time_cycle_minutes is None (not missing, not 0)
    assert retrieved_cycle.dead_time_cycle_minutes is None
