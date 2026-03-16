"""Tests for HALhsStorage adapter (formerly HAModelStorage).

This adapter implements ILhsStorage by using Home Assistant's storage helper
to persist the learned heating slope (LHS).
"""

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

# This import will change from HAModelStorage to HALhsStorage after refactoring
try:
    from custom_components.intelligent_heating_pilot.infrastructure.adapters.lhs_storage import (
        DEFAULT_HEATING_SLOPE,
        HALhsStorage,
    )

    LHS_STORAGE_AVAILABLE = True
except ImportError:
    # Fallback during migration - use old names
    try:
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
            DEFAULT_HEATING_SLOPE,
        )
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
            HAModelStorage as HALhsStorage,
        )

        LHS_STORAGE_AVAILABLE = True
    except ImportError:
        LHS_STORAGE_AVAILABLE = False
        HALhsStorage = None  # type: ignore


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
def mock_store() -> Mock:
    """Create a mock Store."""
    store_mock = Mock()
    store_mock.async_load = AsyncMock(return_value=None)
    store_mock.async_save = AsyncMock()
    return store_mock


@pytest.fixture
async def storage(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HALhsStorage:
    """Create storage adapter with mocked dependencies."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        storage_obj = HALhsStorage(mock_hass, entry_id)
        await storage_obj._ensure_loaded()
        return storage_obj


pytestmark = pytest.mark.skipif(
    not LHS_STORAGE_AVAILABLE,
    reason="HALhsStorage not yet available (migration in progress)",
)


class TestHALhsStorageInheritance:
    """Test that HALhsStorage correctly inherits from BaseHAStorageAdapter.

    These tests verify the refactoring: HALhsStorage should extend
    BaseHAStorageAdapter and use its common functionality.
    """

    def test_inherits_from_base_storage_adapter(self) -> None:
        """Verify HALhsStorage extends BaseHAStorageAdapter.

        This test will FAIL until refactoring is complete.
        """
        try:
            from custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage import (
                BaseHAStorageAdapter,
            )

            assert issubclass(HALhsStorage, BaseHAStorageAdapter)
        except ImportError:
            pytest.skip("BaseHAStorageAdapter not yet implemented")

    def test_implements_lhs_storage_interface(self) -> None:
        """Verify HALhsStorage implements ILhsStorage interface."""
        try:
            from custom_components.intelligent_heating_pilot.domain.interfaces.lhs_storage_interface import (
                ILhsStorage,
            )

            assert issubclass(HALhsStorage, ILhsStorage)
        except ImportError:
            pytest.fail("ILhsStorage interface not found")

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
            storage = HALhsStorage(mock_hass, entry_id)

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
            storage = HALhsStorage(mock_hass, entry_id)

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
    """Test storage adapter initialization."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path) as mock_store_class:
        storage = HALhsStorage(mock_hass, entry_id)

        assert storage._hass == mock_hass
        assert storage._entry_id == entry_id
        mock_store_class.assert_called_once()


def test_lhs_storage_is_concrete() -> None:
    """Test HALhsStorage is not abstract (implements all interface methods)."""
    assert inspect.isabstract(HALhsStorage) is False


@pytest.mark.asyncio
async def test_get_learned_heating_slope_default(storage: HALhsStorage) -> None:
    """Test getting default LHS when not set."""
    lhs = await storage.get_learned_heating_slope()
    assert lhs == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_get_learned_heating_slope_cached(storage: HALhsStorage) -> None:
    """Test getting cached LHS."""
    # Set a custom LHS using the new cached_global_lhs format
    from datetime import datetime

    custom_lhs = 3.5
    storage._data["cached_global_lhs"] = {
        "value": custom_lhs,
        "updated_at": datetime.now().isoformat(),
    }

    lhs = await storage.get_learned_heating_slope()
    assert lhs == custom_lhs


@pytest.mark.asyncio
async def test_get_learned_heating_slope_invalid_returns_default(storage: HALhsStorage) -> None:
    """Test that invalid LHS values return default."""
    from datetime import datetime

    # Set an invalid (too low) LHS using new format
    # MINIMUM_REALISTIC_LHS = 0.2, so 0.15 is below threshold
    storage._data["cached_global_lhs"] = {
        "value": 0.15,  # Below MINIMUM_REALISTIC_LHS (0.2)
        "updated_at": datetime.now().isoformat(),
    }

    lhs = await storage.get_learned_heating_slope()
    assert lhs == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_clear_slope_history(storage: HALhsStorage, mock_store: Mock) -> None:
    """Test clearing learned slope history."""
    from datetime import datetime

    # Set a custom LHS using new cached_global_lhs format
    storage._data["cached_global_lhs"] = {
        "value": 3.5,
        "updated_at": datetime.now().isoformat(),
    }

    # Clear history
    await storage.clear_slope_history()

    # Should reset cached_global_lhs to None
    assert storage._data["cached_global_lhs"] is None
    # And get_learned_heating_slope should return DEFAULT
    lhs = await storage.get_learned_heating_slope()
    assert lhs == DEFAULT_HEATING_SLOPE

    # Should persist to store
    mock_store.async_save.assert_called_once()


@pytest.mark.asyncio
async def test_initialization_with_stored_lhs(
    mock_hass: Mock, entry_id: str, mock_store: Mock
) -> None:
    """Test initialization with previously stored LHS."""
    from datetime import datetime

    stored_lhs = 2.8
    # Use the current storage format: cached_global_lhs dict with value/updated_at
    mock_store.async_load = AsyncMock(
        return_value={
            "cached_global_lhs": {
                "value": stored_lhs,
                "updated_at": datetime.now().isoformat(),
            },
            "cached_contextual_lhs": {},
            "learned_dead_time": None,
        }
    )

    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        storage = HALhsStorage(mock_hass, entry_id)
        await storage._ensure_loaded()

        lhs = await storage.get_learned_heating_slope()
        assert lhs == stored_lhs


@pytest.mark.asyncio
async def test_get_cached_global_lhs_none(storage: HALhsStorage) -> None:
    """Test getting global LHS cache when not set."""
    result = await storage.get_cached_global_lhs()
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_cached_global_lhs(storage: HALhsStorage, mock_store: Mock) -> None:
    """Test setting and getting global LHS cache."""
    lhs_value = 2.8
    now = datetime.now(timezone.utc)

    # Set cache
    await storage.set_cached_global_lhs(lhs_value, now)

    # Verify it was saved
    mock_store.async_save.assert_called()

    # Get cache
    cached = await storage.get_cached_global_lhs()
    assert cached is not None
    assert cached.value == lhs_value
    assert cached.hour is None
    assert abs((cached.updated_at - now).total_seconds()) < 1  # Should be very close


@pytest.mark.asyncio
async def test_get_cached_contextual_lhs_none(storage: HALhsStorage) -> None:
    """Test getting contextual LHS cache when not set."""
    result = await storage.get_cached_contextual_lhs(10)
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_cached_contextual_lhs(storage: HALhsStorage, mock_store: Mock) -> None:
    """Test setting and getting contextual LHS cache."""
    lhs_value = 3.2
    hour = 14
    now = datetime.now(timezone.utc)

    # Set cache
    await storage.set_cached_contextual_lhs(hour, lhs_value, now)

    # Verify it was saved
    mock_store.async_save.assert_called()

    # Get cache
    cached = await storage.get_cached_contextual_lhs(hour)
    assert cached is not None
    assert cached.value == lhs_value
    assert cached.hour == hour
    assert abs((cached.updated_at - now).total_seconds()) < 1


@pytest.mark.asyncio
async def test_clear_contextual_cache(storage: HALhsStorage, mock_store: Mock) -> None:
    """Test clearing contextual LHS cache."""
    await storage.set_cached_contextual_lhs(8, 2.6, datetime.now())
    await storage.set_cached_contextual_lhs(12, 3.1, datetime.now())

    await storage.clear_contextual_cache()

    assert await storage.get_cached_contextual_lhs(8) is None
    assert await storage.get_cached_contextual_lhs(12) is None
    mock_store.async_save.assert_called()


@pytest.mark.asyncio
async def test_contextual_cache_retention_disabled_noop(
    mock_hass: Mock, entry_id: str, mock_store: Mock
) -> None:
    """Test contextual cache operations are no-ops when retention is disabled."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        storage = HALhsStorage(mock_hass, entry_id, retention_days=0)

        await storage.set_cached_contextual_lhs(6, 2.9, datetime.now())
        result = await storage.get_cached_contextual_lhs(6)

        assert result is None
        mock_store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_cached_contextual_lhs_multiple_hours(storage: HALhsStorage) -> None:
    """Test that contextual LHS cache works for multiple hours independently."""
    # Set cache for different hours
    await storage.set_cached_contextual_lhs(10, 2.5, datetime.now())
    await storage.set_cached_contextual_lhs(14, 3.0, datetime.now())
    await storage.set_cached_contextual_lhs(18, 2.8, datetime.now())

    # Verify each hour has its own cache
    cache_10 = await storage.get_cached_contextual_lhs(10)
    cache_14 = await storage.get_cached_contextual_lhs(14)
    cache_18 = await storage.get_cached_contextual_lhs(18)

    assert cache_10 is not None and cache_10.value == 2.5 and cache_10.hour == 10
    assert cache_14 is not None and cache_14.value == 3.0 and cache_14.hour == 14
    assert cache_18 is not None and cache_18.value == 2.8 and cache_18.hour == 18

    # Non-existent hour should return None
    cache_22 = await storage.get_cached_contextual_lhs(22)
    assert cache_22 is None


@pytest.mark.asyncio
async def test_deserialize_invalid_cache_entry(storage: HALhsStorage) -> None:
    """Test that invalid cache entries return None."""
    # Test with empty dict
    result = storage._deserialize_lhs_cache_entry({})
    assert result is None

    # Test with missing value
    result = storage._deserialize_lhs_cache_entry({"updated_at": "2026-01-27T10:00:00"})
    assert result is None

    # Test with missing updated_at
    result = storage._deserialize_lhs_cache_entry({"value": 2.5})
    assert result is None

    # Test with invalid date format
    result = storage._deserialize_lhs_cache_entry({"value": 2.5, "updated_at": "invalid-date"})
    assert result is None


@pytest.mark.asyncio
async def test_serialize_deserialize_roundtrip(storage: HALhsStorage) -> None:
    """Test that serialization/deserialization is reversible."""
    original_value = 2.75
    original_time = datetime.now(timezone.utc)

    # Serialize
    serialized = storage._serialize_lhs_cache_entry(original_value, original_time)

    # Deserialize
    deserialized = storage._deserialize_lhs_cache_entry(serialized, hour=12)

    assert deserialized is not None
    assert deserialized.value == original_value
    assert deserialized.hour == 12
    # Times should be very close (within a second due to serialization)
    assert abs((deserialized.updated_at - original_time).total_seconds()) < 1
