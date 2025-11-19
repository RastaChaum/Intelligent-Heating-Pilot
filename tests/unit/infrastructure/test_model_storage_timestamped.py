"""Tests for HAModelStorage adapter with timestamped slope data."""
import unittest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta, timezone

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import SlopeData


class TestHAModelStorageTimestamped(unittest.TestCase):
    """Tests for HAModelStorage with timestamped data."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.entry_id = "test_entry_123"
        
        # Mock the Store class
        with patch('custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage.Store') as mock_store_class:
            self.mock_store = Mock()
            self.mock_store.async_load = AsyncMock(return_value=None)
            self.mock_store.async_save = AsyncMock()
            mock_store_class.return_value = self.mock_store
            
            self.storage = HAModelStorage(self.mock_hass, self.entry_id, retention_days=30)
    
    def test_save_slope_data(self):
        """Test saving timestamped slope data."""
        import asyncio
        
        # Mock: empty storage
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Create slope data
        timestamp = datetime.now(timezone.utc)
        slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
        
        # Execute
        asyncio.run(self.storage.save_slope_data(slope_data))
        
        # Assert
        self.mock_store.async_save.assert_called_once()
        self.assertEqual(len(self.storage._data["slope_data_list"]), 1)
        
        stored = self.storage._data["slope_data_list"][0]
        self.assertEqual(stored["slope_value"], 2.5)
        self.assertEqual(stored["timestamp"], timestamp.isoformat())
    
    def test_get_all_slope_data(self):
        """Test retrieving all slope data with timestamps."""
        import asyncio
        
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute
        result = asyncio.run(self.storage.get_all_slope_data())
        
        # Assert
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], SlopeData)
        self.assertEqual(result[0].slope_value, 2.0)
        self.assertEqual(result[1].slope_value, 2.2)
        self.assertEqual(result[2].slope_value, 2.1)
    
    def test_get_slopes_in_time_window(self):
        """Test retrieving slopes within a time window."""
        import asyncio
        
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: get slopes in 6-hour window before now
        result = asyncio.run(self.storage.get_slopes_in_time_window(
            before_time=now,
            window_hours=6.0
        ))
        
        # Assert: should get 3 slopes (5h, 3h, 1h ago)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].slope_value, 2.2)  # 5h ago
        self.assertEqual(result[1].slope_value, 2.3)  # 3h ago
        self.assertEqual(result[2].slope_value, 2.1)  # 1h ago
    
    def test_get_slopes_in_time_window_empty(self):
        """Test retrieving slopes when window has no data."""
        import asyncio
        
        # Mock: storage with old data only
        now = datetime.now(timezone.utc)
        stored_data = {
            "slope_data_list": [
                {"timestamp": (now - timedelta(hours=20)).isoformat(), "slope_value": 2.0},
                {"timestamp": (now - timedelta(hours=15)).isoformat(), "slope_value": 2.2},
            ],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: get slopes in 6-hour window before now
        result = asyncio.run(self.storage.get_slopes_in_time_window(
            before_time=now,
            window_hours=6.0
        ))
        
        # Assert: should be empty
        self.assertEqual(len(result), 0)
    
    def test_migration_from_v1_to_v2(self):
        """Test migration from old float list to timestamped data."""
        import asyncio
        
        # Mock: v1 storage with float list
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1, 2.3],
            "learned_heating_slope": 2.15
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: load should trigger migration
        asyncio.run(self.storage._ensure_loaded())
        
        # Assert: should have migrated to v2 format
        self.assertIn("slope_data_list", self.storage._data)
        slope_data_list = self.storage._data["slope_data_list"]
        self.assertEqual(len(slope_data_list), 4)
        
        # All entries should have timestamp and slope_value
        for entry in slope_data_list:
            self.assertIn("timestamp", entry)
            self.assertIn("slope_value", entry)
            self.assertIsInstance(entry["slope_value"], float)
    
    def test_cleanup_old_data(self):
        """Test cleanup of data older than retention period."""
        import asyncio
        
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
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: load should trigger cleanup
        asyncio.run(self.storage._ensure_loaded())
        
        # Assert: old data (>30 days) should be removed
        slope_data_list = self.storage._data["slope_data_list"]
        self.assertEqual(len(slope_data_list), 2)  # Only 20d and 5d ago remain
        self.assertEqual(slope_data_list[0]["slope_value"], 2.0)
        self.assertEqual(slope_data_list[1]["slope_value"], 2.2)
    
    def test_backward_compatible_save_slope_in_history(self):
        """Test that old save_slope_in_history method still works."""
        import asyncio
        
        # Mock: empty storage
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Execute: use old method
        asyncio.run(self.storage.save_slope_in_history(2.5))
        
        # Assert: should create timestamped entry
        self.mock_store.async_save.assert_called_once()
        slope_data_list = self.storage._data["slope_data_list"]
        self.assertEqual(len(slope_data_list), 1)
        self.assertEqual(slope_data_list[0]["slope_value"], 2.5)
        self.assertIn("timestamp", slope_data_list[0])
    
    def test_backward_compatible_get_slopes_in_history(self):
        """Test that old get_slopes_in_history method still works."""
        import asyncio
        
        # Mock: storage with new format
        now = datetime.now(timezone.utc)
        stored_data = {
            "slope_data_list": [
                {"timestamp": (now - timedelta(hours=2)).isoformat(), "slope_value": 2.0},
                {"timestamp": (now - timedelta(hours=1)).isoformat(), "slope_value": 2.2},
            ],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: use old method
        result = asyncio.run(self.storage.get_slopes_in_history())
        
        # Assert: should return float list
        self.assertEqual(result, [2.0, 2.2])


if __name__ == "__main__":
    unittest.main()
