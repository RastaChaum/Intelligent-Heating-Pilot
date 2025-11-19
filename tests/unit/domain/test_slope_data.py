"""Tests for SlopeData value object."""
import unittest
from datetime import datetime, timezone

import sys
import os

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects import SlopeData


class TestSlopeData(unittest.TestCase):
    """Tests for SlopeData value object."""
    
    def test_create_valid_slope_data(self):
        """Test creating valid SlopeData."""
        timestamp = datetime.now(timezone.utc)
        slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
        
        self.assertEqual(slope_data.slope_value, 2.5)
        self.assertEqual(slope_data.timestamp, timestamp)
    
    def test_slope_data_is_immutable(self):
        """Test that SlopeData is immutable."""
        timestamp = datetime.now(timezone.utc)
        slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
        
        # Should not be able to modify
        with self.assertRaises(AttributeError):
            slope_data.slope_value = 3.0
    
    def test_negative_slope_raises_error(self):
        """Test that negative slopes are rejected."""
        timestamp = datetime.now(timezone.utc)
        
        with self.assertRaises(ValueError) as context:
            SlopeData(slope_value=-1.0, timestamp=timestamp)
        
        self.assertIn("must be positive", str(context.exception))
    
    def test_zero_slope_raises_error(self):
        """Test that zero slopes are rejected."""
        timestamp = datetime.now(timezone.utc)
        
        with self.assertRaises(ValueError) as context:
            SlopeData(slope_value=0.0, timestamp=timestamp)
        
        self.assertIn("must be positive", str(context.exception))
    
    def test_naive_timestamp_raises_error(self):
        """Test that naive timestamps are rejected."""
        timestamp = datetime.now()  # Naive datetime
        
        with self.assertRaises(ValueError) as context:
            SlopeData(slope_value=2.5, timestamp=timestamp)
        
        self.assertIn("timezone-aware", str(context.exception))
    
    def test_equality(self):
        """Test that SlopeData equality works correctly."""
        timestamp = datetime.now(timezone.utc)
        slope_data1 = SlopeData(slope_value=2.5, timestamp=timestamp)
        slope_data2 = SlopeData(slope_value=2.5, timestamp=timestamp)
        
        self.assertEqual(slope_data1, slope_data2)
    
    def test_inequality(self):
        """Test that different SlopeData are not equal."""
        timestamp1 = datetime.now(timezone.utc)
        timestamp2 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        
        slope_data1 = SlopeData(slope_value=2.5, timestamp=timestamp1)
        slope_data2 = SlopeData(slope_value=2.5, timestamp=timestamp2)
        slope_data3 = SlopeData(slope_value=3.0, timestamp=timestamp1)
        
        self.assertNotEqual(slope_data1, slope_data2)
        self.assertNotEqual(slope_data1, slope_data3)


if __name__ == "__main__":
    unittest.main()
