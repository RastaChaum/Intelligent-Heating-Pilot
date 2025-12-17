"""Tests for HAModelStorage adapter."""
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
    MAX_HISTORY_SIZE,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.slope_data import SlopeData


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
def storage(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HAModelStorage:
    """Create a HAModelStorage instance with mocked Store."""
    with patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store') as mock_store_class:
        mock_store_class.return_value = mock_store
        storage_instance = HAModelStorage(mock_hass, entry_id)
        yield storage_instance


def test_init(storage: HAModelStorage, entry_id: str, mock_hass: Mock) -> None:
    """Test adapter initialization."""
    assert storage._entry_id == entry_id
    assert storage._hass == mock_hass
    assert not storage._loaded


def test_init_with_custom_retention_days(mock_hass: Mock, entry_id: str) -> None:
    """Test initialization with custom retention days."""
    custom_retention = 60
    with patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store'):
        storage = HAModelStorage(mock_hass, entry_id, retention_days=custom_retention)
        assert storage._retention_days == custom_retention


@pytest.mark.asyncio
async def test_get_learned_heating_slope_default(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting LHS when no history exists."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    result = await storage.get_learned_heating_slope()
    
    assert result == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_get_learned_heating_slope_with_v2_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting LHS with v2 format historical data."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=2)).isoformat(), "slope_value": 2.1},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=3)).isoformat(), "slope_value": 2.3},
        ],
        "learned_heating_slope": 2.15
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_learned_heating_slope()
    
    assert result == 2.15


@pytest.mark.asyncio
async def test_get_learned_heating_slope_with_v1_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting LHS with v1 format (legacy) historical data."""
    stored_data = {
        "historical_slopes": [2.0, 2.2, 2.1, 2.3],
        "learned_heating_slope": 2.15
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_learned_heating_slope()
    
    assert result == 2.15


@pytest.mark.asyncio
async def test_save_slope_data_positive(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test saving a positive heating slope with v2 format."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    slope_value = 2.5
    now = datetime.now(tz=ZoneInfo("UTC"))
    await storage.save_slope_data(SlopeData(slope_value=slope_value, timestamp=now))
    
    mock_store.async_save.assert_called_once()
    assert len(storage._data["slope_data_list"]) == 1
    assert storage._data["slope_data_list"][0]["slope_value"] == slope_value


@pytest.mark.asyncio
async def test_save_slope_in_history_positive(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test deprecated save_slope_in_history method with positive slope."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    slope_value = 2.5
    await storage.save_slope_data(SlopeData(slope_value=slope_value, timestamp=datetime.now(tz=ZoneInfo("UTC"))))
    
    mock_store.async_save.assert_called_once()
    assert len(storage._data["slope_data_list"]) == 1
    assert storage._data["slope_data_list"][0]["slope_value"] == slope_value


def test_save_slope_in_history_negative_ignored() -> None:
    """Test that negative slopes raise ValueError."""
    with pytest.raises(ValueError):
        SlopeData(slope_value=-1.5, timestamp=datetime.now(tz=ZoneInfo("UTC")))


def test_save_slope_in_history_zero_ignored() -> None:
    """Test that zero slopes are ignored (non-positive)."""
    with pytest.raises(ValueError):
        SlopeData(slope_value=0.0, timestamp=datetime.now(tz=ZoneInfo("UTC")))


@pytest.mark.asyncio
async def test_save_slope_data_trimming(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that slope history is trimmed to MAX_HISTORY_SIZE."""
    initial_slope_data = [
        {
            "timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=i)).isoformat(),
            "slope_value": float(i) + 1
        }
        for i in range(MAX_HISTORY_SIZE + 10)
    ]
    stored_data = {
        "slope_data_list": initial_slope_data,
        "learned_heating_slope": 50.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.save_slope_data(
        SlopeData(slope_value=2.0, timestamp=datetime.now(tz=ZoneInfo("UTC")))
    )
    
    assert len(storage._data["slope_data_list"]) == MAX_HISTORY_SIZE


@pytest.mark.asyncio
async def test_get_slopes_in_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting historical slopes (v2 format)."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=2)).isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_slopes_in_history()
    
    assert result == [2.0, 2.2, 2.1]
    result.append(999)
    assert 999 not in [e["slope_value"] for e in storage._data["slope_data_list"]]


@pytest.mark.asyncio
async def test_get_slopes_in_history_v1_legacy(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting historical slopes from v1 format (legacy fallback)."""
    stored_data = {
        "historical_slopes": [2.0, 2.2, 2.1],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_slopes_in_history()
    
    assert result == [2.0, 2.2, 2.1]


@pytest.mark.asyncio
async def test_get_slopes_in_history_empty(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting slopes when history is empty."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    result = await storage.get_slopes_in_history()
    
    assert result == []


@pytest.mark.asyncio
async def test_get_all_slope_data(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting all slope data with timestamps."""
    now = datetime.now(tz=ZoneInfo("UTC"))
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            {"timestamp": now.isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_all_slope_data()
    
    assert len(result) == 3
    assert isinstance(result[0], SlopeData)
    assert result[0].slope_value == 2.0
    assert result[2].slope_value == 2.1


@pytest.mark.asyncio
async def test_get_all_slope_data_empty(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test getting all slope data when none exists."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    result = await storage.get_all_slope_data()
    
    assert result == []


@pytest.mark.asyncio
async def test_get_slopes_in_time_window(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test retrieving slopes within a specific time window."""
    now = datetime.now(tz=ZoneInfo("UTC"))
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=5)).isoformat(), "slope_value": 1.0},
            {"timestamp": (now - timedelta(hours=3)).isoformat(), "slope_value": 2.0},
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.5},
            {"timestamp": now.isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_slopes_in_time_window(
        before_time=now,
        window_hours=3
    )
    
    assert len(result) == 2
    assert result[0].slope_value == 2.0
    assert result[1].slope_value == 2.5


@pytest.mark.asyncio
async def test_get_slopes_in_time_window_empty(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test time window query returns empty list when no data in window."""
    now = datetime.now(tz=ZoneInfo("UTC"))
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=10)).isoformat(), "slope_value": 1.0},
        ],
        "learned_heating_slope": 1.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_slopes_in_time_window(
        before_time=now - timedelta(hours=5),
        window_hours=2
    )
    
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_slopes_in_time_window_boundary_conditions(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test time window boundary conditions (exclusive before_time)."""
    now = datetime.now(tz=ZoneInfo("UTC"))
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(hours=3)).isoformat(), "slope_value": 1.0},
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "slope_value": 2.0},
            {"timestamp": now.isoformat(), "slope_value": 3.0},
        ],
        "learned_heating_slope": 2.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    # Query with before_time exactly at one entry (should be exclusive)
    result = await storage.get_slopes_in_time_window(
        before_time=now,
        window_hours=2
    )
    
    assert len(result) == 1
    assert result[0].slope_value == 2.0


@pytest.mark.asyncio
async def test_clear_slope_history(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test clearing all slope history."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.get_learned_heating_slope()
    await storage.clear_slope_history()
    
    assert storage._data["slope_data_list"] == []
    assert storage._data["learned_heating_slope"] == DEFAULT_HEATING_SLOPE
    mock_store.async_save.assert_called()


@pytest.mark.asyncio
async def test_migration_v1_to_v2(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test migration from v1 format to v2 format."""
    stored_data = {
        "historical_slopes": [1.0, 2.0, 3.0],
        "learned_heating_slope": 2.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.get_learned_heating_slope()
    
    assert "slope_data_list" in storage._data
    assert len(storage._data["slope_data_list"]) == 3
    assert "historical_slopes" not in storage._data


@pytest.mark.asyncio
async def test_migration_v1_empty_list(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test migration from v1 with empty slope list."""
    stored_data = {
        "historical_slopes": [],
        "learned_heating_slope": 2.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.get_learned_heating_slope()
    
    assert storage._data["slope_data_list"] == []


@pytest.mark.asyncio
async def test_cleanup_old_data(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that old slope data is automatically cleaned up."""
    now = datetime.now(tz=ZoneInfo("UTC"))
    stored_data = {
        "slope_data_list": [
            {"timestamp": (now - timedelta(days=40)).isoformat(), "slope_value": 1.0},
            {"timestamp": (now - timedelta(days=10)).isoformat(), "slope_value": 2.0},
            {"timestamp": now.isoformat(), "slope_value": 2.5},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.get_learned_heating_slope()
    
    assert len(storage._data["slope_data_list"]) == 2
    assert storage._data["slope_data_list"][0]["slope_value"] == 2.0


@pytest.mark.asyncio
async def test_cleanup_respects_retention_period(mock_hass: Mock, entry_id: str) -> None:
    """Test cleanup respects custom retention period."""
    custom_retention = 5
    mock_store = Mock()
    mock_store.async_load = AsyncMock(return_value=None)
    mock_store.async_save = AsyncMock()
    
    with patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store') as mock_store_class:
        mock_store_class.return_value = mock_store
        storage = HAModelStorage(mock_hass, entry_id, retention_days=custom_retention)
        
        now = datetime.now(tz=ZoneInfo("UTC"))
        stored_data = {
            "slope_data_list": [
                {"timestamp": (now - timedelta(days=10)).isoformat(), "slope_value": 1.0},
                {"timestamp": (now - timedelta(days=3)).isoformat(), "slope_value": 2.0},
                {"timestamp": now.isoformat(), "slope_value": 2.5},
            ],
            "learned_heating_slope": 2.1
        }
        
        mock_store.async_load = AsyncMock(return_value=stored_data)
        await storage.get_learned_heating_slope()
        
        assert len(storage._data["slope_data_list"]) == 2


@pytest.mark.asyncio
async def test_invalid_slope_entry_handling(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test graceful handling of invalid slope entries."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
            {"timestamp": "invalid-timestamp", "slope_value": 2.2},
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat()},
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.1},
        ],
        "learned_heating_slope": 2.1
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_all_slope_data()
    
    assert len(result) == 2
    assert result[0].slope_value == 2.0
    assert result[1].slope_value == 2.1


@pytest.mark.asyncio
async def test_multiple_loads_use_cache(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that multiple loads use cached data (not reloading from store)."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
        ],
        "learned_heating_slope": 2.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    await storage.get_learned_heating_slope()
    await storage.get_slopes_in_history()
    
    # async_load should only be called once due to caching
    assert mock_store.async_load.call_count == 1


@pytest.mark.asyncio
async def test_save_updates_lhs_calculation(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that saving slope data updates the LHS calculation."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    # Save multiple slopes and verify LHS is recalculated
    slopes = [2.0, 2.2, 2.1]
    for slope in slopes:
        await storage.save_slope_data(
            SlopeData(slope_value=slope, timestamp=datetime.now(tz=ZoneInfo("UTC")))
        )
    
    lhs = storage._data["learned_heating_slope"]
    assert lhs > 0
    assert lhs != DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_empty_positive_slopes_uses_default(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that when no positive slopes exist, default LHS is returned."""
    stored_data = {
        "slope_data_list": [
            {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": -1.0},
            {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": -2.0},
        ],
        "learned_heating_slope": -1.0
    }
    mock_store.async_load = AsyncMock(return_value=stored_data)
    
    result = await storage.get_learned_heating_slope()
    
    assert result == DEFAULT_HEATING_SLOPE


@pytest.mark.asyncio
async def test_large_slope_values_handled(storage: HAModelStorage, mock_store: Mock) -> None:
    """Test that unusually large slope values are stored correctly."""
    mock_store.async_load = AsyncMock(return_value=None)
    
    large_slope = 99.99
    await storage.save_slope_data(
        SlopeData(slope_value=large_slope, timestamp=datetime.now(tz=ZoneInfo("UTC")))
    )
    
    assert storage._data["slope_data_list"][0]["slope_value"] == large_slope
