"""Tests for prediction service."""
import unittest
from datetime import timedelta

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

from domain.services import PredictionService

# Import fixtures
sys.path.insert(0, os.path.dirname(__file__))
from fixtures import (
    get_test_datetime,
    get_future_datetime,
    TEST_CURRENT_TEMP,
    TEST_TARGET_TEMP,
    TEST_OUTDOOR_TEMP,
    TEST_HUMIDITY,
    TEST_LEARNED_SLOPE,
)


class TestPredictionService(unittest.TestCase):
    """Tests for PredictionService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = PredictionService()

    def test_predict_heating_time_basic(self):
        """Test basic heating time prediction."""
        target_time = get_future_datetime(2)
        
        result = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            outdoor_temp=TEST_OUTDOOR_TEMP,
            humidity=TEST_HUMIDITY,
        )
        
        # Should have valid result
        self.assertIsNotNone(result)
        self.assertGreater(result.estimated_duration_minutes, 0)
        self.assertGreater(result.confidence_level, 0)
        self.assertEqual(result.learned_heating_slope, TEST_LEARNED_SLOPE)
        
        # Anticipated start should be before target
        self.assertLess(result.anticipated_start_time, target_time)

    def test_predict_no_heating_needed(self):
        """Test prediction when already at target temperature."""
        target_time = get_future_datetime(2)
        
        result = self.service.predict_heating_time(
            current_temp=21.0,
            target_temp=21.0,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
        )
        
        # Should return zero duration and target_time as anticipated_start
        self.assertEqual(result.estimated_duration_minutes, 0.0)
        self.assertEqual(result.confidence_level, 1.0)
        self.assertEqual(result.anticipated_start_time, target_time)

    def test_high_humidity_increases_duration(self):
        """Test that high humidity increases heating duration."""
        target_time = get_future_datetime(2)
        
        # Normal humidity
        result_normal = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            humidity=50.0,
        )
        
        # High humidity
        result_high = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            humidity=75.0,
        )
        
        # High humidity should increase duration
        self.assertGreater(
            result_high.estimated_duration_minutes,
            result_normal.estimated_duration_minutes
        )

    def test_cloud_coverage_increases_duration(self):
        """Test that high cloud coverage increases heating duration."""
        target_time = get_future_datetime(2)
        
        # Clear sky
        result_clear = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            cloud_coverage=10.0,
        )
        
        # Overcast
        result_cloudy = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            cloud_coverage=90.0,
        )
        
        # Clouds should increase duration
        self.assertGreater(
            result_cloudy.estimated_duration_minutes,
            result_clear.estimated_duration_minutes
        )

    def test_respects_min_anticipation_time(self):
        """Test that minimum anticipation time is enforced."""
        target_time = get_future_datetime(2)
        
        # Very small temperature difference with high slope
        result = self.service.predict_heating_time(
            current_temp=20.9,
            target_temp=21.0,
            learned_slope=10.0,
            target_time=target_time,
        )
        
        # Should respect minimum
        self.assertGreaterEqual(
            result.estimated_duration_minutes,
            self.service.MIN_ANTICIPATION_TIME
        )

    def test_respects_max_anticipation_time(self):
        """Test that maximum anticipation time is enforced."""
        target_time = get_future_datetime(5)
        
        # Large temperature difference with slow slope
        result = self.service.predict_heating_time(
            current_temp=10.0,
            target_temp=25.0,
            learned_slope=0.5,
            target_time=target_time,
            humidity=80.0,
        )
        
        # Should respect maximum
        self.assertLessEqual(
            result.estimated_duration_minutes,
            self.service.MAX_ANTICIPATION_TIME
        )

    def test_handles_invalid_slope(self):
        """Test handling of invalid (zero or negative) slope."""
        target_time = get_future_datetime(2)
        
        # Zero slope should return zero confidence
        result = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=0.0,
            target_time=target_time,
        )
        
        # Should return target_time and zero confidence
        self.assertEqual(result.anticipated_start_time, target_time)
        self.assertEqual(result.confidence_level, 0.0)


if __name__ == "__main__":
    unittest.main()
