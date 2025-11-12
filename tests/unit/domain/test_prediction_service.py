"""Tests for prediction service."""
import unittest
from datetime import datetime, timedelta

import sys
import os

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/smart_starter_vtherm",
    ),
)

from domain.services import PredictionService


class TestPredictionService(unittest.TestCase):
    """Tests for PredictionService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = PredictionService()

    def test_predict_heating_time_basic(self):
        """Test basic heating time prediction."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        result = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=2.0,
            target_time=target_time,
        )
        
        # Should have valid result
        self.assertIsNotNone(result)
        self.assertGreater(result.estimated_duration_minutes, 0)
        self.assertGreater(result.confidence_level, 0)
        self.assertEqual(result.learned_heating_slope, 2.0)
        
        # Anticipated start should be before target
        self.assertLess(result.anticipated_start_time, target_time)

    def test_predict_no_heating_needed(self):
        """Test prediction when already at target temperature."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        result = self.service.predict_heating_time(
            current_temp=21.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=2.0,
            target_time=target_time,
        )
        
        # Should return zero duration
        self.assertEqual(result.estimated_duration_minutes, 0.0)
        self.assertEqual(result.confidence_level, 1.0)

    def test_high_humidity_increases_duration(self):
        """Test that high humidity increases heating duration."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        # Normal humidity
        result_normal = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=2.0,
            target_time=target_time,
        )
        
        # High humidity
        result_high = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=75.0,  # High humidity
            learned_slope=2.0,
            target_time=target_time,
        )
        
        # High humidity should increase duration
        self.assertGreater(
            result_high.estimated_duration_minutes,
            result_normal.estimated_duration_minutes
        )

    def test_cloud_coverage_increases_duration(self):
        """Test that high cloud coverage increases heating duration."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        # Clear sky
        result_clear = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=2.0,
            target_time=target_time,
            cloud_coverage=10.0,
        )
        
        # Overcast
        result_cloudy = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=2.0,
            target_time=target_time,
            cloud_coverage=90.0,  # Overcast
        )
        
        # Clouds should increase duration
        self.assertGreater(
            result_cloudy.estimated_duration_minutes,
            result_clear.estimated_duration_minutes
        )

    def test_respects_min_anticipation_time(self):
        """Test that minimum anticipation time is enforced."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        # Very small temperature difference with high slope
        result = self.service.predict_heating_time(
            current_temp=20.9,
            target_temp=21.0,
            outdoor_temp=20.0,
            humidity=50.0,
            learned_slope=10.0,  # Very fast heating
            target_time=target_time,
        )
        
        # Should respect minimum
        self.assertGreaterEqual(
            result.estimated_duration_minutes,
            self.service.MIN_ANTICIPATION_TIME
        )

    def test_respects_max_anticipation_time(self):
        """Test that maximum anticipation time is enforced."""
        now = datetime.now()
        target_time = now + timedelta(hours=5)
        
        # Large temperature difference with slow slope
        result = self.service.predict_heating_time(
            current_temp=10.0,
            target_temp=25.0,
            outdoor_temp=-10.0,
            humidity=80.0,
            learned_slope=0.5,  # Very slow heating
            target_time=target_time,
        )
        
        # Should respect maximum
        self.assertLessEqual(
            result.estimated_duration_minutes,
            self.service.MAX_ANTICIPATION_TIME
        )

    def test_handles_invalid_slope(self):
        """Test handling of invalid (zero or negative) slope."""
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        # Zero slope should fall back to default
        result = self.service.predict_heating_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            humidity=50.0,
            learned_slope=0.0,  # Invalid
            target_time=target_time,
        )
        
        # Should still return valid result with fallback slope
        self.assertGreater(result.estimated_duration_minutes, 0)


if __name__ == "__main__":
    unittest.main()
