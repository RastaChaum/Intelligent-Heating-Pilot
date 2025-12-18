"""Tests for HAModelStorage adapter (simplified after removing slope persistence)."""
from unittest.mock import Mock, AsyncMock, patch

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
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
async def test_initialization_with_stored_lhs(mock_hass: Mock, entry_id: str, mock_store: Mock) -> None:
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
