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
    
    def test_calculate_contextual_lhs_with_time_window(self):
        """Test calculating contextual LHS based on time window."""
        from datetime import timedelta
        
        # Create slopes over 10 hours
        target_time = datetime(2025, 11, 17, 18, 0, 0, tzinfo=timezone.utc)
        slope_data_list = [
            SlopeData(slope_value=1.8, timestamp=target_time - timedelta(hours=10)),
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=8)),
            SlopeData(slope_value=2.2, timestamp=target_time - timedelta(hours=5)),  # In 6h window
            SlopeData(slope_value=2.3, timestamp=target_time - timedelta(hours=3)),  # In 6h window
            SlopeData(slope_value=2.1, timestamp=target_time - timedelta(hours=1)),  # In 6h window
        ]
        
        # Calculate with 6-hour window
        result = self.service.calculate_contextual_lhs(
            all_slope_data=slope_data_list,
            target_time=target_time,
            window_hours=6.0
        )
        
        # Should only use slopes from last 6 hours (2.2, 2.3, 2.1)
        # Average should be around 2.2
        self.assertGreater(result, 2.0)
        self.assertLess(result, 2.4)
    
    def test_calculate_contextual_lhs_empty_window(self):
        """Test contextual LHS when no slopes in window."""
        from datetime import timedelta
        
        # Create slopes but all outside the window
        target_time = datetime(2025, 11, 17, 18, 0, 0, tzinfo=timezone.utc)
        slope_data_list = [
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=20)),
            SlopeData(slope_value=2.2, timestamp=target_time - timedelta(hours=15)),
        ]
        
        # Calculate with 6-hour window
        result = self.service.calculate_contextual_lhs(
            all_slope_data=slope_data_list,
            target_time=target_time,
            window_hours=6.0
        )
        
        # Should return default when no slopes in window
        self.assertEqual(result, 2.0)
    
    def test_calculate_contextual_lhs_empty_data(self):
        """Test contextual LHS with no data."""
        target_time = datetime(2025, 11, 17, 18, 0, 0, tzinfo=timezone.utc)
        
        result = self.service.calculate_contextual_lhs(
            all_slope_data=[],
            target_time=target_time,
            window_hours=6.0
        )
        
        # Should return default
        self.assertEqual(result, 2.0)
    
    def test_calculate_contextual_lhs_filters_correctly(self):
        """Test that contextual LHS correctly filters by time window."""
        from datetime import timedelta
        
        target_time = datetime(2025, 11, 17, 18, 0, 0, tzinfo=timezone.utc)
        
        # Create slopes: some in window, some outside
        slope_data_list = [
            SlopeData(slope_value=1.0, timestamp=target_time - timedelta(hours=7)),  # Outside
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=5)),  # Inside
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=4)),  # Inside
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=3)),  # Inside
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=2)),  # Inside
            SlopeData(slope_value=2.0, timestamp=target_time - timedelta(hours=1)),  # Inside
        ]
        
        result = self.service.calculate_contextual_lhs(
            all_slope_data=slope_data_list,
            target_time=target_time,
            window_hours=6.0
        )
        
        # Should only average the 5 slopes in window (all 2.0)
        # Should not include the 1.0 slope from 7 hours ago
        self.assertAlmostEqual(result, 2.0, places=2)


if __name__ == "__main__":
    unittest.main()
