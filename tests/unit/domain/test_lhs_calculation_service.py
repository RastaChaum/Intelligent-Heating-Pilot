"""Tests for LHSCalculationService."""
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

from domain.services import LHSCalculationService
from domain.value_objects import SlopeData


class TestLHSCalculationService(unittest.TestCase):
    """Tests for LHS calculation service."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = LHSCalculationService()
    
    def test_calculate_robust_average_empty_list(self):
        """Test calculating average with empty list."""
        result = self.service.calculate_robust_average([])
        
        # Should return default
        self.assertEqual(result, 2.0)
    
    def test_calculate_robust_average_few_values(self):
        """Test calculating average with less than 4 values (no trimming)."""
        values = [2.0, 2.1, 2.2]
        result = self.service.calculate_robust_average(values)
        
        # Should return simple average
        expected = sum(values) / len(values)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_calculate_robust_average_with_trimming(self):
        """Test calculating average with trimming (>= 4 values)."""
        # 7 values: outliers at both ends
        values = [1.0, 2.0, 2.1, 2.2, 2.3, 2.4, 10.0]
        result = self.service.calculate_robust_average(values)
        
        # Outlier 1.0 and 10.0 should be removed
        # Result should be average of middle values
        self.assertGreater(result, 1.5)
        self.assertLess(result, 3.0)
    
    def test_calculate_robust_average_trimmed_mean(self):
        """Test trimmed mean calculation removes outliers."""
        # 10 values with clear outliers
        values = [0.5, 1.8, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 3.0, 15.0]
        result = self.service.calculate_robust_average(values)
        
        # Top and bottom 10% (1 value each) should be removed
        # 0.5 and 15.0 should be excluded
        # Average should be around 2.2-2.3
        self.assertGreater(result, 1.8)
        self.assertLess(result, 2.8)
    
    def test_calculate_from_slope_data_empty(self):
        """Test calculating from empty SlopeData list."""
        result = self.service.calculate_from_slope_data([])
        
        # Should return default
        self.assertEqual(result, 2.0)
    
    def test_calculate_from_slope_data(self):
        """Test calculating from SlopeData objects."""
        timestamp = datetime.now(timezone.utc)
        slope_data_list = [
            SlopeData(slope_value=2.0, timestamp=timestamp),
            SlopeData(slope_value=2.2, timestamp=timestamp),
            SlopeData(slope_value=2.1, timestamp=timestamp),
        ]
        
        result = self.service.calculate_from_slope_data(slope_data_list)
        
        # Should calculate average
        expected = (2.0 + 2.2 + 2.1) / 3
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_calculate_from_slope_data_with_outliers(self):
        """Test calculating from SlopeData with outliers."""
        timestamp = datetime.now(timezone.utc)
        slope_data_list = [
            SlopeData(slope_value=1.0, timestamp=timestamp),  # Outlier
            SlopeData(slope_value=2.0, timestamp=timestamp),
            SlopeData(slope_value=2.1, timestamp=timestamp),
            SlopeData(slope_value=2.2, timestamp=timestamp),
            SlopeData(slope_value=2.3, timestamp=timestamp),
            SlopeData(slope_value=10.0, timestamp=timestamp), # Outlier
        ]
        
        result = self.service.calculate_from_slope_data(slope_data_list)
        
        # Outliers should be removed
        self.assertGreater(result, 1.5)
        self.assertLess(result, 3.0)


if __name__ == "__main__":
    unittest.main()
