"""Tests for the Smart Starter VTherm calculator."""
import unittest
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../custom_components/smart_starter_vtherm'))

# Import directly from calculator.py without going through __init__.py
from calculator import PreheatingCalculator


class TestPreheatingCalculator(unittest.TestCase):
    """Test cases for PreheatingCalculator."""

    def setUp(self):
        """Set up test fixtures."""
        self.calculator = PreheatingCalculator(thermal_slope=2.0)

    def test_no_preheat_needed_when_already_at_target(self):
        """Test that no preheating is needed when already at target temperature."""
        duration = self.calculator.calculate_preheat_duration(
            current_temp=21.0,
            target_temp=21.0,
            outdoor_temp=10.0
        )
        self.assertEqual(duration, 0.0)

    def test_no_preheat_needed_when_above_target(self):
        """Test that no preheating is needed when above target temperature."""
        duration = self.calculator.calculate_preheat_duration(
            current_temp=22.0,
            target_temp=21.0,
            outdoor_temp=10.0
        )
        self.assertEqual(duration, 0.0)

    def test_basic_preheat_calculation(self):
        """Test basic preheating calculation with neutral outdoor conditions."""
        # At 20°C outdoor temp, outdoor_factor should be 1.0
        # To heat 3°C with slope of 2.0°C/h: 3/2 = 1.5 hours = 90 minutes
        duration = self.calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=20.0
        )
        self.assertAlmostEqual(duration, 90.0, places=1)

    def test_cold_outdoor_increases_duration(self):
        """Test that cold outdoor temperature increases preheating duration."""
        # At 0°C outdoor: factor = 1 + (20-0)*0.05 = 2.0
        # Effective slope = 2.0 / 2.0 = 1.0°C/h
        # To heat 3°C: 3/1 = 3 hours = 180 minutes
        duration = self.calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=0.0
        )
        self.assertAlmostEqual(duration, 180.0, places=1)

    def test_very_cold_outdoor(self):
        """Test preheating calculation with very cold outdoor temperature."""
        # At -10°C outdoor: factor = 1 + (20-(-10))*0.05 = 2.5
        # Effective slope = 2.0 / 2.5 = 0.8°C/h
        # To heat 3°C: 3/0.8 = 3.75 hours = 225 minutes
        duration = self.calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=-10.0
        )
        self.assertAlmostEqual(duration, 225.0, places=1)

    def test_warm_outdoor_decreases_duration(self):
        """Test that warm outdoor temperature decreases preheating duration."""
        # At 25°C outdoor: factor = 1 + (20-25)*0.05 = 0.75, min 0.5 -> 0.75
        # Effective slope = 2.0 / 0.75 = 2.67°C/h
        # To heat 3°C: 3/2.67 = 1.125 hours = 67.5 minutes
        duration = self.calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=25.0
        )
        self.assertLess(duration, 90.0)  # Should be less than neutral case

    def test_calculate_start_time_future(self):
        """Test start time calculation when enough time is available."""
        target_time = datetime.now() + timedelta(hours=3)
        result = self.calculator.calculate_start_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            target_time=target_time
        )
        
        self.assertIn("start_time", result)
        self.assertIn("preheat_duration_minutes", result)
        self.assertIn("should_start_now", result)
        self.assertIsInstance(result["start_time"], datetime)
        self.assertFalse(result["should_start_now"])
        self.assertEqual(result["current_temp"], 18.0)
        self.assertEqual(result["target_temp"], 21.0)
        self.assertEqual(result["outdoor_temp"], 10.0)

    def test_calculate_start_time_past(self):
        """Test start time calculation when heating should start now."""
        target_time = datetime.now() + timedelta(minutes=30)
        result = self.calculator.calculate_start_time(
            current_temp=15.0,
            target_temp=21.0,
            outdoor_temp=5.0,
            target_time=target_time
        )
        
        # With 6°C to heat and cold outdoor, duration will be > 30 min
        self.assertTrue(result["should_start_now"])

    def test_different_thermal_slopes(self):
        """Test that different thermal slopes affect calculation."""
        slow_calculator = PreheatingCalculator(thermal_slope=1.0)
        fast_calculator = PreheatingCalculator(thermal_slope=4.0)
        
        slow_duration = slow_calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=20.0
        )
        
        fast_duration = fast_calculator.calculate_preheat_duration(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=20.0
        )
        
        # Slower slope should require more time
        self.assertGreater(slow_duration, fast_duration)
        # Fast should be half the time of slow (4.0 vs 1.0)
        self.assertAlmostEqual(slow_duration / fast_duration, 4.0, places=1)

    def test_large_temperature_difference(self):
        """Test calculation with large temperature difference."""
        duration = self.calculator.calculate_preheat_duration(
            current_temp=10.0,
            target_temp=22.0,
            outdoor_temp=15.0
        )
        # Should calculate correctly even with 12°C difference
        self.assertGreater(duration, 0)
        self.assertIsInstance(duration, float)

    def test_result_structure(self):
        """Test that calculate_start_time returns all expected fields."""
        target_time = datetime.now() + timedelta(hours=2)
        result = self.calculator.calculate_start_time(
            current_temp=18.0,
            target_temp=21.0,
            outdoor_temp=10.0,
            target_time=target_time
        )
        
        expected_keys = {
            "start_time",
            "preheat_duration_minutes",
            "should_start_now",
            "target_time",
            "current_temp",
            "target_temp",
            "outdoor_temp"
        }
        self.assertEqual(set(result.keys()), expected_keys)


if __name__ == '__main__':
    unittest.main()
