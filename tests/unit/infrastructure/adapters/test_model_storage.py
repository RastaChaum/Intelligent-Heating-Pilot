"""Tests for HAModelStorage adapter."""
import unittest
from unittest.mock import Mock, AsyncMock, patch

from custom_components.intelligent_heating_pilot.infrastructure.adapters.model_storage import (
    HAModelStorage,
    DEFAULT_HEATING_SLOPE,
)


class TestHAModelStorage(unittest.TestCase):
    """Tests for HAModelStorage adapter."""
    
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
            
            self.storage = HAModelStorage(self.mock_hass, self.entry_id)
    
    def test_init(self):
        """Test adapter initialization."""
        self.assertEqual(self.storage._entry_id, self.entry_id)
        self.assertEqual(self.storage._hass, self.mock_hass)
        self.assertFalse(self.storage._loaded)
    
    def test_get_learned_heating_slope_default(self):
        """Test getting LHS when no history exists."""
        import asyncio
        
        # Mock: no stored data
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Execute
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        # Assert
        self.assertEqual(result, DEFAULT_HEATING_SLOPE)
    
    def test_get_learned_heating_slope_with_history(self):
        """Test getting LHS with historical data."""
        import asyncio
        
        # Mock: stored data with history
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1, 2.3],
            "learned_heating_slope": 2.15
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute
        result = asyncio.run(self.storage.get_learned_heating_slope())
        
        # Assert
        self.assertEqual(result, 2.15)
    
    def test_save_slope_in_history_positive(self):
        """Test saving a positive heating slope."""
        import asyncio
        
        # Mock: empty storage
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Execute
        asyncio.run(self.storage.save_slope_in_history(2.5))
        
        # Assert
        self.mock_store.async_save.assert_called_once()
        self.assertIn(2.5, self.storage._data["historical_slopes"])
    
    def test_save_slope_in_history_negative_ignored(self):
        """Test that negative slopes are ignored."""
        import asyncio
        
        # Mock: empty storage
        self.mock_store.async_load = AsyncMock(return_value=None)
        
        # Execute
        asyncio.run(self.storage.save_slope_in_history(-1.5))
        
        # Assert: save should not be called for negative slope
        self.mock_store.async_save.assert_not_called()
    
    def test_save_slope_in_history_trimming(self):
        """Test that history is trimmed to MAX_HISTORY_SIZE."""
        import asyncio
        from infrastructure.adapters.model_storage import MAX_HISTORY_SIZE
        
        # Mock: storage with many slopes
        initial_slopes = [float(i) for i in range(1, MAX_HISTORY_SIZE + 10)]
        stored_data = {
            "historical_slopes": initial_slopes,
            "learned_heating_slope": 50.0
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute: add one more slope
        asyncio.run(self.storage.save_slope_in_history(2.0))
        
        # Assert: history should be trimmed
        self.assertEqual(len(self.storage._data["historical_slopes"]), MAX_HISTORY_SIZE)
    
    def test_get_slopes_in_history(self):
        """Test getting historical slopes."""
        import asyncio
        
        # Mock: stored data with slopes
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Execute
        result = asyncio.run(self.storage.get_slopes_in_history())
        
        # Assert
        self.assertEqual(result, [2.0, 2.2, 2.1])
        # Should return a copy, not the original
        result.append(999)
        self.assertNotIn(999, self.storage._data["historical_slopes"])
    
    def test_clear_slope_history(self):
        """Test clearing all slope history."""
        import asyncio
        
        # Mock: stored data with slopes
        stored_data = {
            "historical_slopes": [2.0, 2.2, 2.1],
            "learned_heating_slope": 2.1
        }
        self.mock_store.async_load = AsyncMock(return_value=stored_data)
        
        # Load first
        asyncio.run(self.storage.get_learned_heating_slope())
        
        # Execute
        asyncio.run(self.storage.clear_slope_history())
        
        # Assert
        self.assertEqual(self.storage._data["historical_slopes"], [])
        self.assertEqual(self.storage._data["learned_heating_slope"], DEFAULT_HEATING_SLOPE)
        self.mock_store.async_save.assert_called_once()
    
    def test_calculate_robust_average_trimmed_mean(self):
        """Test robust average calculation with trimming."""
        # Test with enough values for trimming (>= 4)
        values = [1.0, 2.0, 2.1, 2.2, 2.3, 2.4, 10.0]  # 10.0 is outlier
        
        result = self.storage._calculate_robust_average(values)
        
        # Outlier should be removed, average should be around 2.0-2.4
        self.assertGreater(result, 1.5)
        self.assertLess(result, 3.0)
    
    def test_calculate_robust_average_simple(self):
        """Test robust average with few values (no trimming)."""
        values = [2.0, 2.1, 2.2]
        
        result = self.storage._calculate_robust_average(values)
        
        # Should be simple average
        expected = sum(values) / len(values)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_calculate_robust_average_empty(self):
        """Test robust average with empty list."""
        result = self.storage._calculate_robust_average([])
        
        self.assertEqual(result, DEFAULT_HEATING_SLOPE)


if __name__ == "__main__":
    unittest.main()
