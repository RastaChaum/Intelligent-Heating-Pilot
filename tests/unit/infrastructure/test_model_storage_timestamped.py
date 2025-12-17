"""Tests for HAModelStorage adapter with timestamped slope data."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch
from typing import Generator

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import SlopeData


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
    """Create a mock Store instance."""
    store = Mock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    return store


@pytest.fixture
def storage(mock_hass: Mock, entry_id: str, mock_store: Mock) -> Generator[HAModelStorage, None, None]:
    """Create a HAModelStorage instance with timestamped slope data."""
    with patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store') as mock_store_class:
        mock_store_class.return_value = mock_store
        storage_instance = HAModelStorage(mock_hass, entry_id, retention_days=30)
        yield storage_instance


@pytest.mark.asyncio
async def test_save_slope_data(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test saving timestamped slope data."""
    # Mock: empty storage
    mock_store.async_load = AsyncMock(return_value=None)
    
    # Create slope data
    timestamp = datetime.now(timezone.utc)
    slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
    
    # Execute
    await storage.save_slope_data(slope_data)
    
    # Assert
    mock_store.async_save.assert_called_once()
    assert len(storage._data["slope_data_list"]) == 1
    
    stored = storage._data["slope_data_list"][0]
    assert stored["slope_value"] == 2.5
    assert stored["timestamp"] == timestamp.isoformat()


@pytest.mark.asyncio
async def test_get_all_slope_data(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test retrieving all slope data with timestamps."""
    # Mock: storage with timestamped data
    now = datetime.now(timezone.utc)
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            {"timestamp": now.isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute
    result = await storage.get_all_slope_data()
    
    # Assert
    assert len(result) == 3
    assert isinstance(result[0], SlopeData)
    assert result[0].slope_value == 2.0
    assert result[1].slope_value == 2.2
    assert result[2].slope_value == 2.1


@pytest.mark.asyncio
async def test_get_slopes_in_time_window(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test retrieving slopes within a time window."""
    # Mock: storage with timestamped data over 10 hours
    now = datetime.now(timezone.utc)
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=10)).isoformat(), "slope_value": 1.8},
            {"timestamp": (now - timedelta(hours=8)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=5)).isoformat(), "slope_value": 2.2},
            {"timestamp": (now - timedelta(hours=3)).isoformat(), "slope_value": 2.3},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute: get slopes in 6-hour window before now
    result = await storage.get_slopes_in_time_window(
        before_time=now,
        window_hours=6.0
    )
    
    # Assert: should get 3 slopes (5h, 3h, 1h ago)
    assert len(result) == 3
    assert result[0].slope_value == 2.2  # 5h ago
    assert result[1].slope_value == 2.3  # 3h ago
    assert result[2].slope_value == 2.1  # 1h ago


@pytest.mark.asyncio
async def test_get_slopes_in_time_window_empty(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test retrieving slopes when window has no data."""
    # Mock: storage with old data only
    now = datetime.now(timezone.utc)
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=20)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=15)).isoformat(), "slope_value": 2.2},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute: get slopes in 6-hour window before now
    result = await storage.get_slopes_in_time_window(
        before_time=now,
        window_hours=6.0
    )
    
    # Assert: should be empty
    assert len(result) == 0


@pytest.mark.asyncio
async def test_migration_from_v1_to_v2(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test migration from old float list to timestamped data."""
    # Mock: v1 storage with float list
    stored_data = {
        "historical_slopes": [2.0, 2.2, 2.1, 2.3],
        "learned_heating_slope": 2.15
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute: load should trigger migration
    await storage._ensure_loaded()
    
    # Assert: should have migrated to v2 format
    assert "slope_data_list" in storage._data
    slope_data_list = storage._data["slope_data_list"]
    assert len(slope_data_list) == 4
    
    # All entries should have timestamp and slope_value
    for entry in slope_data_list:
        assert "timestamp" in entry
        assert "slope_value" in entry
        assert isinstance(entry["slope_value"], float)


@pytest.mark.asyncio
async def test_cleanup_old_data(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test cleanup of data older than retention period."""
    # Mock: storage with old and new data
    now = datetime.now(timezone.utc)
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(days=40)).isoformat(), "slope_value": 1.5},
            {"timestamp": (now - timedelta(days=35)).isoformat(), "slope_value": 1.8},
            {"timestamp": (now - timedelta(days=20)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(days=5)).isoformat(), "slope_value": 2.2},
        ],
        "learned_heating_slope": 2.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute: load should trigger cleanup
    await storage._ensure_loaded()
    
    # Assert: old data (>30 days) should be removed
    slope_data_list = storage._data["slope_data_list"]
    assert len(slope_data_list) == 2  # Only 20d and 5d ago remain
    assert slope_data_list[0]["slope_value"] == 2.0
    assert slope_data_list[1]["slope_value"] == 2.2


@pytest.mark.asyncio
async def test_backward_compatible_save_slope_in_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that old save_slope_in_history method still works."""
    # Mock: empty storage
    mock_store.async_load = AsyncMock(return_value=None)
    
    # Execute: use old method
    await storage.save_slope_in_history(2.5)
    
    # Assert: should create timestamped entry
    mock_store.async_save.assert_called_once()
    slope_data_list = storage._data["slope_data_list"]
    assert len(slope_data_list) == 1
    assert slope_data_list[0]["slope_value"] == 2.5
    assert "timestamp" in slope_data_list[0]


@pytest.mark.asyncio
async def test_backward_compatible_get_slopes_in_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that old get_slopes_in_history method still works."""
    # Mock: storage with new format
    now = datetime.now(timezone.utc)
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Execute: use old method
    result = await storage.get_slopes_in_history()
    
    # Assert: should return float list
    assert result == [2.0, 2.2]
