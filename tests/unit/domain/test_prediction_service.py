"""Tests for prediction service."""

import unittest
from datetime import timedelta

from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_ANTICIPATION_BUFFER,
    MAX_ANTICIPATION_TIME,
    MIN_ANTICIPATION_TIME,
)
from custom_components.intelligent_heating_pilot.domain.services import PredictionService
from custom_components.intelligent_heating_pilot.domain.value_objects import DaylightPeriod

# Import fixtures
from tests.unit.domain.fixtures import (
    TEST_CURRENT_TEMP,
    TEST_HUMIDITY,
    TEST_LEARNED_SLOPE,
    TEST_TARGET_TEMP,
    get_future_datetime,
)

HEATING_MINUTES = (TEST_TARGET_TEMP - TEST_CURRENT_TEMP) / TEST_LEARNED_SLOPE * 60.0
CLEAR_SKY = 0.0
OVERCAST_SKY = 100.0


def _daylight_around(target_time):
    """A daylight period covering the whole heating phase before ``target_time``."""
    return DaylightPeriod(target_time - timedelta(hours=6), target_time + timedelta(hours=1))


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
        """In daylight, high cloud coverage increases heating duration."""
        target_time = get_future_datetime(2)
        daylight = [_daylight_around(target_time)]

        # Clear sky
        result_clear = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            cloud_coverage=10.0,
            daylight_periods=daylight,
        )

        # Overcast
        result_cloudy = self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=target_time,
            cloud_coverage=90.0,
            daylight_periods=daylight,
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
        assert result.estimated_duration_minutes >= expected_base_duration - 5, (
            f"Duration {result.estimated_duration_minutes} below expected {expected_base_duration} - 5"
        )
        assert result.estimated_duration_minutes <= expected_base_duration + 15, (
            f"Duration {result.estimated_duration_minutes} exceeds expected {expected_base_duration} + 15"
        )

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
        assert duration_diff >= dead_time_minutes - 1.0, (
            f"Dead time effect ({duration_diff}) should be ~{dead_time_minutes}"
        )


class TestEnvironmentalCorrectionScope(unittest.TestCase):
    """The correction applies to the heating phase only, the sun only in daylight (#257)."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = PredictionService()
        self.target_time = get_future_datetime(4)

    def _duration(self, **kwargs) -> float:
        kwargs.setdefault("dead_time_minutes", 0.0)
        return self.service.predict_heating_time(
            current_temp=TEST_CURRENT_TEMP,
            target_temp=TEST_TARGET_TEMP,
            learned_slope=TEST_LEARNED_SLOPE,
            target_time=self.target_time,
            **kwargs,
        ).estimated_duration_minutes

    def test_humidity_does_not_scale_the_dead_time(self):
        """A dead time adds exactly its value, whatever the humidity."""
        without = self._duration(humidity=80.0)
        with_dead_time = self._duration(humidity=80.0, dead_time_minutes=60.0)
        self.assertAlmostEqual(with_dead_time - without, 60.0)

    def test_sun_does_not_scale_the_dead_time(self):
        """A dead time adds exactly its value under a clear sky in daylight."""
        daylight = [_daylight_around(self.target_time)]
        without = self._duration(cloud_coverage=CLEAR_SKY, daylight_periods=daylight)
        with_dead_time = self._duration(
            cloud_coverage=CLEAR_SKY, daylight_periods=daylight, dead_time_minutes=60.0
        )
        self.assertAlmostEqual(with_dead_time - without, 60.0)

    def test_clear_sky_in_daylight_shortens_the_heating_phase(self):
        """The full solar factor applies when the heating phase is in daylight."""
        duration = self._duration(
            cloud_coverage=CLEAR_SKY, daylight_periods=[_daylight_around(self.target_time)]
        )
        self.assertAlmostEqual(duration, HEATING_MINUTES * 0.9 + DEFAULT_ANTICIPATION_BUFFER)

    def test_no_daylight_period_means_no_solar_gain(self):
        """Unknown sun position: a clear sky does not shorten the preheat."""
        clear = self._duration(cloud_coverage=CLEAR_SKY)
        overcast = self._duration(cloud_coverage=OVERCAST_SKY)
        self.assertAlmostEqual(clear, overcast)

    def test_daylight_after_the_target_time_brings_no_solar_gain(self):
        """A sunrise after the target time does not shorten the preheat."""
        after = DaylightPeriod(
            self.target_time + timedelta(minutes=10), self.target_time + timedelta(hours=9)
        )
        clear = self._duration(cloud_coverage=CLEAR_SKY, daylight_periods=[after])
        self.assertAlmostEqual(clear, HEATING_MINUTES + DEFAULT_ANTICIPATION_BUFFER)

    def test_solar_gain_is_prorated_over_two_daylight_periods(self):
        """A heating phase across sunset and the next sunrise sums both overlaps."""
        heating_start = self.target_time - timedelta(minutes=HEATING_MINUTES)
        periods = [
            DaylightPeriod(
                heating_start - timedelta(hours=8), heating_start + timedelta(minutes=9)
            ),
            DaylightPeriod(
                self.target_time - timedelta(minutes=18), self.target_time + timedelta(hours=8)
            ),
        ]
        duration = self._duration(cloud_coverage=CLEAR_SKY, daylight_periods=periods)
        # 27 of 90 minutes in daylight: 30 % of the 10 % solar shortening.
        expected = HEATING_MINUTES * (1 - 0.1 * 0.3) + DEFAULT_ANTICIPATION_BUFFER
        self.assertAlmostEqual(duration, expected)


if __name__ == "__main__":
    unittest.main()
