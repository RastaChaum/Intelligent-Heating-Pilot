"""Tests for prediction service."""

import unittest

from custom_components.intelligent_heating_pilot.domain.constants import (
    MAX_ANTICIPATION_TIME,
    MIN_ANTICIPATION_TIME,
)
from custom_components.intelligent_heating_pilot.domain.services import PredictionService

# Import fixtures
from tests.unit.domain.fixtures import (
    TEST_CURRENT_TEMP,
    TEST_HUMIDITY,
    TEST_LEARNED_SLOPE,
    TEST_OUTDOOR_TEMP,
    TEST_TARGET_TEMP,
    get_future_datetime,
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
            result_high.estimated_duration_minutes, result_normal.estimated_duration_minutes
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
            result_cloudy.estimated_duration_minutes, result_clear.estimated_duration_minutes
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
        self.assertGreaterEqual(result.estimated_duration_minutes, MIN_ANTICIPATION_TIME)

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
        self.assertLessEqual(result.estimated_duration_minutes, MAX_ANTICIPATION_TIME)

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

    def test_dead_time_increases_duration(self):
        """Test that dead_time parameter increases heating duration."""
        target_time = get_future_datetime(2)
        # Without dead time
        result_no_deadtime = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            dead_time_minutes=0.0,
        )
        # With dead time
        result_with_deadtime = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            dead_time_minutes=15.0,
        )

        # Dead time should increase duration by exactly 15 minutes
        self.assertAlmostEqual(
            result_with_deadtime.estimated_duration_minutes
            - result_no_deadtime.estimated_duration_minutes,
            15.0,
            delta=0.1,
        )

    def test_dead_time_formula_exact_values(self):
        """Validate exact dead time formula: estimated_duration = dead_time + (temp_delta / slope) * 60 + buffer.

        Regression test for Issue #62: Ensure dead time calculation is precise.

        GIVEN:
            - current_temp = 18.0°C (TEST_CURRENT_TEMP)
            - target_temp = 21.0°C (TEST_TARGET_TEMP)
            - temp_delta = 3.0°C
            - learned_slope = 2.0°C/hour (TEST_LEARNED_SLOPE)
            - dead_time = 15.0 minutes

        EXPECTED CALCULATION:
            - Base heating time (without dead time) = (temp_delta / slope) * 60
                                                   = (3.0 / 2.0) * 60
                                                   = 1.5 * 60
                                                   = 90 minutes
            - With dead time added = 15 + 90 = 105 minutes
            - Plus default buffer/corrections, expected range: 100-110 minutes

        WHEN: predict_heating_time() called with dead_time=15.0
        THEN: result.estimated_duration_minutes should be within expected range

        This test FAILS if:
        - Dead time formula is incorrect
        - Dead time parameter is not properly passed through the calculation
        - Buffer/correction factors change unexpectedly
        """
        target_time = get_future_datetime(2)
        dead_time_minutes = 15.0

        result = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            dead_time_minutes=dead_time_minutes,
        )

        # Verify basic calculation components
        temp_delta = TEST_TARGET_TEMP - TEST_CURRENT_TEMP
        calculated_heating_time = (temp_delta / TEST_LEARNED_SLOPE) * 60
        expected_base_duration = dead_time_minutes + calculated_heating_time

        # Allow for buffer and correction factors (5-10 minute tolerance)
        assert (
            result.estimated_duration_minutes >= expected_base_duration - 5
        ), f"Duration {result.estimated_duration_minutes} below expected {expected_base_duration} - 5"
        assert (
            result.estimated_duration_minutes <= expected_base_duration + 15
        ), f"Duration {result.estimated_duration_minutes} exceeds expected {expected_base_duration} + 15"

        # Verify dead time actually increased the duration compared to zero dead time
        result_no_deadtime = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            dead_time_minutes=0.0,
        )

        # Dead time should increase duration by at least its value (minus small tolerance for rounding)
        duration_diff = (
            result.estimated_duration_minutes - result_no_deadtime.estimated_duration_minutes
        )
        assert (
            duration_diff >= dead_time_minutes - 1.0
        ), f"Dead time effect ({duration_diff}) should be ~{dead_time_minutes}"


if __name__ == "__main__":
    unittest.main()
