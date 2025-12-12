"""Tests for HAModelStorage adapter."""
import asyncio
from datetime import datetime, timedelta
import unittest
from unittest.mock import Mock, AsyncMock, patch, call
from zoneinfo import ZoneInfo

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
    MAX_HISTORY_SIZE,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.slope_data import SlopeData


class TestHAModelStorage(unittest.TestCase):
    """Tests for HAModelStorage adapter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.entry_id = "test_entry_123"
        self.mock_store = Mock()
        self.mock_store.async_load = AsyncMock(return_value=None)
        self.mock_store.async_save = AsyncMock()
        
        # Patch the Store class at module level
        self.patcher = patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store')
        self.mock_store_class = self.patcher.start()
        self.mock_store_class.return_value = self.mock_store
        
        self.storage = HAModelStorage(self.mock_hass, self.entry_id)
    
    def tearDown(self):
        """Clean up patches."""
        self.patcher.stop()
    
    def test_init(self):
        """Test adapter initialization."""
        self.assertEqual(self.storage._entry_id, self.entry_id)
        self.assertEqual(self.storage._hass, self.mock_hass)
        self.assertFalse(self.storage._loaded)
    
    def test_init_with_custom_retention_days(self):
        """Test initialization with custom retention days."""
        custom_retention = 60
        storage = HAModelStorage(self.mock_hass, self.entry_id, retention_days=custom_retention)
        self.assertEqual(storage._retention_days, custom_retention)
    
    def test_get_learned_heating_slope_default(self):
        """Test getting LHS when no history exists."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(result, DEFAULT_HEATING_SLOPE)
    
    def test_get_learned_heating_slope_with_v2_history(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(result, 2.15)
    
    def test_get_learned_heating_slope_with_v1_history(self):
        """Test getting LHS with v1 format (legacy) historical data."""
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1, 2.3],
            "learned_heating_slope": 2.15
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(result, 2.15)
    
    def test_save_slope_data_positive(self):
        """Test saving a positive heating slope with v2 format."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        slope_value = 2.5
        now = datetime.now(tz=ZoneInfo("UTC"))
        asyncio.run(self.storage.save_slope_data(SlopeData(slope_value=slope_value, timestamp=now)))
        
        self.mock_store.async_save.assert_called_once()
        self.assertEqual(len(self.storage._data["slope_data_list"]), 1)
        self.assertEqual(self.storage._data["slope_data_list"][0]["slope_value"], slope_value)
    
    def test_save_slope_in_history_positive(self):
        """Test deprecated save_slope_in_history method with positive slope."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        slope_value = 2.5
        asyncio.run(self.storage.save_slope_data(SlopeData(slope_value=slope_value, timestamp=datetime.now(tz=ZoneInfo("UTC")))))
        
        self.mock_store.async_save.assert_called_once()
        self.assertEqual(len(self.storage._data["slope_data_list"]), 1)
        self.assertEqual(self.storage._data["slope_data_list"][0]["slope_value"], slope_value)
    
    def test_save_slope_in_history_negative_ignored(self):
        """Test that negative slopes raise ValueError."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        with self.assertRaises(ValueError):
            SlopeData(slope_value=-1.5, timestamp=datetime.now(tz=ZoneInfo("UTC")))
    
    def test_save_slope_in_history_zero_ignored(self):
        """Test that zero slopes are ignored (non-positive)."""
        self.mock_store.async_load = AsyncMock(return_value=None)

        with self.assertRaises(ValueError):
            SlopeData(slope_value=0.0, timestamp=datetime.now(tz=ZoneInfo("UTC")))
    
    def test_save_slope_data_trimming(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.save_slope_data(
            SlopeData(slope_value=2.0, timestamp=datetime.now(tz=ZoneInfo("UTC")))
        ))
        
        self.assertEqual(len(self.storage._data["slope_data_list"]), MAX_HISTORY_SIZE)
    
    def test_get_slopes_in_history(self):
        """Test getting historical slopes (v2 format)."""
        stored_data = {
            "slope_data_list": [
                {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
                {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
                {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=2)).isoformat(), "slope_value": 2.1},
            ],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_slopes_in_history())
        
        self.assertEqual(result, [2.0, 2.2, 2.1])
        result.append(999)
        self.assertNotIn(999, [e["slope_value"] for e in self.storage._data["slope_data_list"]])
    
    def test_get_slopes_in_history_v1_legacy(self):
        """Test getting historical slopes from v1 format (legacy fallback)."""
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_slopes_in_history())
        
        self.assertEqual(result, [2.0, 2.2, 2.1])
    
    def test_get_slopes_in_history_empty(self):
        """Test getting slopes when history is empty."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        result = asyncio.run(self.storage.get_slopes_in_history())
        
        self.assertEqual(result, [])
    
    def test_get_all_slope_data(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_all_slope_data())
        
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], SlopeData)
        self.assertEqual(result[0].slope_value, 2.0)
        self.assertEqual(result[2].slope_value, 2.1)
    
    def test_get_all_slope_data_empty(self):
        """Test getting all slope data when none exists."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        result = asyncio.run(self.storage.get_all_slope_data())
        
        self.assertEqual(result, [])
    
    def test_get_slopes_in_time_window(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_slopes_in_time_window(
            before_time=now,
            window_hours=3
        ))
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].slope_value, 2.0)
        self.assertEqual(result[1].slope_value, 2.5)
    
    def test_get_slopes_in_time_window_empty(self):
        """Test time window query returns empty list when no data in window."""
        now = datetime.now(tz=ZoneInfo("UTC"))
        stored_data = {
            "slope_data_list": [
                {"timestamp": (now - timedelta(hours=10)).isoformat(), "slope_value": 1.0},
            ],
            "learned_heating_slope": 1.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_slopes_in_time_window(
            before_time=now - timedelta(hours=5),
            window_hours=2
        ))
        
        self.assertEqual(len(result), 0)
    
    def test_get_slopes_in_time_window_boundary_conditions(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Query with before_time exactly at one entry (should be exclusive)
        result = asyncio.run(self.storage.get_slopes_in_time_window(
            before_time=now,
            window_hours=2
        ))
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].slope_value, 2.0)
    
    def test_clear_slope_history(self):
        """Test clearing all slope history."""
        stored_data = {
            "slope_data_list": [
                {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
                {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            ],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.get_learned_heating_slope())
        asyncio.run(self.storage.clear_slope_history())
        
        self.assertEqual(self.storage._data["slope_data_list"], [])
        self.assertEqual(self.storage._data["learned_heating_slope"], DEFAULT_HEATING_SLOPE)
        self.mock_store.async_save.assert_called()
    
    def test_migration_v1_to_v2(self):
        """Test migration from v1 format to v2 format."""
        stored_data = {
            "historical_slopes": [1.0, 2.0, 3.0],
            "learned_heating_slope": 2.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertIn("slope_data_list", self.storage._data)
        self.assertEqual(len(self.storage._data["slope_data_list"]), 3)
        self.assertNotIn("historical_slopes", self.storage._data)
    
    def test_migration_v1_empty_list(self):
        """Test migration from v1 with empty slope list."""
        stored_data = {
            "historical_slopes": [],
            "learned_heating_slope": 2.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(self.storage._data["slope_data_list"], [])
    
    def test_cleanup_old_data(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(len(self.storage._data["slope_data_list"]), 2)
        self.assertEqual(self.storage._data["slope_data_list"][0]["slope_value"], 2.0)
    
    def test_cleanup_respects_retention_period(self):
        """Test cleanup respects custom retention period."""
        custom_retention = 5
        storage = HAModelStorage(self.mock_hass, self.entry_id, retention_days=custom_retention)
        
        now = datetime.now(tz=ZoneInfo("UTC"))
        stored_data = {
            "slope_data_list": [
                {"timestamp": (now - timedelta(days=10)).isoformat(), "slope_value": 1.0},
                {"timestamp": (now - timedelta(days=3)).isoformat(), "slope_value": 2.0},
                {"timestamp": now.isoformat(), "slope_value": 2.5},
            ],
            "learned_heating_slope": 2.1
        }
        
        with patch.object(storage._store, 'async_load', AsyncMock(return_value=stored_data)):
            with patch.object(storage._store, 'async_save', AsyncMock()):
                asyncio.run(storage.get_learned_heating_slope())
                
                self.assertEqual(len(storage._data["slope_data_list"]), 2)
    
    def test_invalid_slope_entry_handling(self):
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_all_slope_data())
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].slope_value, 2.0)
        self.assertEqual(result[1].slope_value, 2.1)
    
    def test_multiple_loads_use_cache(self):
        """Test that multiple loads use cached data (not reloading from store)."""
        stored_data = {
            "slope_data_list": [
                {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": 2.0},
            ],
            "learned_heating_slope": 2.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        asyncio.run(self.storage.get_learned_heating_slope())
        asyncio.run(self.storage.get_slopes_in_history())
        
        # async_load should only be called once due to caching
        self.assertEqual(self.mock_store.async_load.call_count, 1)
    
    def test_save_updates_lhs_calculation(self):
        """Test that saving slope data updates the LHS calculation."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Save multiple slopes and verify LHS is recalculated
        slopes = [2.0, 2.2, 2.1]
        for slope in slopes:
            asyncio.run(self.storage.save_slope_data(
                SlopeData(slope_value=slope, timestamp=datetime.now(tz=ZoneInfo("UTC")))
            ))
        
        lhs = self.storage._data["learned_heating_slope"]
        self.assertGreater(lhs, 0)
        self.assertNotEqual(lhs, DEFAULT_HEATING_SLOPE)
    
    def test_empty_positive_slopes_uses_default(self):
        """Test that when no positive slopes exist, default LHS is returned."""
        stored_data = {
            "slope_data_list": [
                {"timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "slope_value": -1.0},
                {"timestamp": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(), "slope_value": -2.0},
            ],
            "learned_heating_slope": -1.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        self.assertEqual(result, DEFAULT_HEATING_SLOPE)
    
    def test_large_slope_values_handled(self):
        """Test that unusually large slope values are stored correctly."""
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        large_slope = 99.99
        asyncio.run(self.storage.save_slope_data(
            SlopeData(slope_value=large_slope, timestamp=datetime.now(tz=ZoneInfo("UTC")))
        ))
        
        self.assertEqual(self.storage._data["slope_data_list"][0]["slope_value"], large_slope)


if __name__ == "__main__":
    unittest.main()