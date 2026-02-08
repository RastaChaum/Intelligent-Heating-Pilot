"""Tests for HAModelStorage adapter (simplified after removing slope persistence)."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    DEFAULT_HEATING_SLOPE,
    HAModelStorage,
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
async def storage(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HAModelStorage:
    """Create storage adapter with mocked dependencies."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store",
        return_value=mock_store,
    ):
        storage_obj = HAModelStorage(mock_hass, entry_id)
        await storage_obj._ensure_loaded()
        return storage_obj


def test_init(mock_hass: Mock, entry_id: str) -> None:
    """Test storage adapter initialization."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store"
    ) as mock_store_class:
        storage = HAModelStorage(mock_hass, entry_id)

        assert storage._hass == mock_hass
        assert storage._entry_id == entry_id
        mock_store_class.assert_called_once()


@pytest.mark.asyncio
async def test_get_learned_heating_slope_default(storage: HAModelStorage) -> None:
    """Test getting default LHS when not set."""
    lhs = await storage.get_learned_heating_slope()
    assert lhs == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_get_learned_heating_slope_cached(storage: HAModelStorage) -> None:
    """Test getting cached LHS."""
    # Set a custom LHS
    custom_lhs = 3.5
    storage._data["learned_heating_slope"] = custom_lhs

    lhs = await storage.get_learned_heating_slope()
    assert lhs == custom_lhs


@pytest.mark.asyncio
async def test_get_learned_heating_slope_invalid_returns_default(storage: HAModelStorage) -> None:
    """Test that invalid LHS values return default."""
    # Set an invalid (negative) LHS
    storage._data["learned_heating_slope"] = -1.0

    lhs = await storage.get_learned_heating_slope()
    assert lhs == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_clear_slope_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test clearing learned slope history."""
    # Set a custom LHS
    storage._data["learned_heating_slope"] = 3.5

    # Clear history
    await storage.clear_slope_history()

    # Should be reset to default
    assert storage._data["learned_heating_slope"] == DEFAULT_HEATING_SLOPE

    # Should persist to store
    mock_store.async_save.assert_called_once()


@pytest.mark.asyncio
async def test_initialization_with_stored_lhs(
    mock_hass: Mock, entry_id: str, mock_store: Mock
) -> None:
    """Test initialization with previously stored LHS."""
    stored_lhs = 2.8
    mock_store.async_load = AsyncMock(
        return_value={
            "learned_heating_slope": stored_lhs,
        }
    )

    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store",
        return_value=mock_store,
    ):
        storage = HAModelStorage(mock_hass, entry_id)
        await storage._ensure_loaded()

        lhs = await storage.get_learned_heating_slope()
        assert lhs == stored_lhs


@pytest.mark.asyncio
async def test_get_cached_global_lhs_none(storage: HAModelStorage) -> None:
    """Test getting global LHS cache when not set."""
    result = await storage.get_cached_global_lhs()
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_cached_global_lhs(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test setting and getting global LHS cache."""
    lhs_value = 2.8
    now = datetime.now()

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
async def test_get_cached_contextual_lhs_none(storage: HAModelStorage) -> None:
    """Test getting contextual LHS cache when not set."""
    result = await storage.get_cached_contextual_lhs(10)
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_cached_contextual_lhs(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test setting and getting contextual LHS cache."""
    lhs_value = 3.2
    hour = 14
    now = datetime.now()

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
async def test_cached_contextual_lhs_multiple_hours(storage: HAModelStorage) -> None:
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
async def test_deserialize_invalid_cache_entry(storage: HAModelStorage) -> None:
    """Test that invalid cache entries return None."""
    # Test with empty dict
    result = storage._deserialize_cached_entry({})
    assert result is None

    # Test with missing value
    result = storage._deserialize_cached_entry({"updated_at": "2026-01-27T10:00:00"})
    assert result is None

    # Test with missing updated_at
    result = storage._deserialize_cached_entry({"value": 2.5})
    assert result is None

    # Test with invalid date format
    result = storage._deserialize_cached_entry({"value": 2.5, "updated_at": "invalid-date"})
    assert result is None


@pytest.mark.asyncio
async def test_serialize_deserialize_roundtrip(storage: HAModelStorage) -> None:
    """Test that serialization/deserialization is reversible."""
    original_value = 2.75
    original_time = datetime.now()

    # Serialize
    serialized = storage._serialize_cached_entry(original_value, original_time)

    # Deserialize
    deserialized = storage._deserialize_cached_entry(serialized, hour=12)

    assert deserialized is not None
    assert deserialized.value == original_value
    assert deserialized.hour == 12
    # Times should be very close (within a second due to serialization)
    assert abs((deserialized.updated_at - original_time).total_seconds()) < 1
