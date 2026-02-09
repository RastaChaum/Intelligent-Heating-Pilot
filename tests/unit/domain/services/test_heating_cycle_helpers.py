"""Unit tests for HeatingCycleService helper methods extracted during refactoring."""

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)


def m(
    timestamp: datetime, value: float | str | bool, device_id: str = "test.device"
) -> HistoricalMeasurement:
    """Helper to create HistoricalMeasurement with empty attributes."""
    return HistoricalMeasurement(timestamp, value, {}, device_id)


@pytest.fixture
def service():
    """Create HeatingCycleService instance for testing."""
    return HeatingCycleService(
        temp_delta_threshold=0.5,
        cycle_split_duration_minutes=0,
    )


@pytest.fixture
def base_time():
    """Base timestamp for tests."""
    return datetime(2024, 1, 1, 12, 0, 0)


class TestComputeEnergyKwh:
    """Tests for _compute_energy_kwh helper."""

    def test_with_cumulative_meter_returns_difference(self, service, base_time):
        """Given cumulative energy meter data, returns difference."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {
            HistoricalDataKey.HEATING_ENERGY_KWH: [
                m(start_time, 10.0),
                m(end_time, 12.5),
            ]
        }

        result = service._compute_energy_kwh(data, start_time, end_time)

        assert result == 2.5

    def test_without_energy_data_returns_zero(self, service, base_time):
        """Given no energy meter data, returns 0.0."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {}

        result = service._compute_energy_kwh(data, start_time, end_time)

        assert result == 0.0

    def test_with_negative_difference_returns_zero(self, service, base_time):
        """Given decreasing meter (reset), returns 0.0."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {
            HistoricalDataKey.HEATING_ENERGY_KWH: [
                m(start_time, 12.5),
                m(end_time, 10.0),  # Reset
            ]
        }

        result = service._compute_energy_kwh(data, start_time, end_time)

        assert result == 0.0


class TestComputeRuntimeMinutes:
    """Tests for _compute_runtime_minutes helper."""

    def test_with_runtime_sensor_sums_all_values(self, service, base_time):
        """Given runtime sensor data (non-cumulative), sums all on_time_sec values."""
        start_time = base_time
        mid1 = base_time + timedelta(minutes=5)
        mid2 = base_time + timedelta(minutes=10)
        end_time = base_time + timedelta(minutes=15)
        data = {
            HistoricalDataKey.HEATING_RUNTIME_SECONDS: [
                m(start_time, 120.0),  # 120 sec on_time at 10:00
                m(mid1, 180.0),  # 180 sec on_time at 10:05
                m(mid2, 240.0),  # 240 sec on_time at 10:10
                m(end_time, 150.0),  # 150 sec on_time at 10:15 (reset happened)
            ]
        }

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=60.0
        )

        # Sum of all on_time_sec in range: 120 + 180 + 240 + 150 = 690 sec
        assert result == pytest.approx(690.0 / 60.0)  # 11.5 minutes

    def test_with_no_measurements_in_range_uses_fallback(self, service, base_time):
        """Given no runtime measurements in time range, uses fallback."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {
            HistoricalDataKey.HEATING_RUNTIME_SECONDS: [
                m(base_time - timedelta(hours=1), 300.0),  # Before range
                m(base_time + timedelta(hours=2), 400.0),  # After range
            ]
        }

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=45.0
        )

        assert result == 45.0

    def test_with_partial_measurements_in_range_sums_only_in_range(self, service, base_time):
        """Given measurements spanning wider range, sums only those in [start_time, end_time]."""
        start_time = base_time + timedelta(minutes=5)
        end_time = base_time + timedelta(minutes=15)
        data = {
            HistoricalDataKey.HEATING_RUNTIME_SECONDS: [
                m(base_time, 100.0),  # Before range
                m(start_time, 200.0),  # In range
                m(base_time + timedelta(minutes=10), 150.0),  # In range
                m(end_time, 175.0),  # In range (at boundary)
                m(base_time + timedelta(minutes=20), 300.0),  # After range
            ]
        }

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=60.0
        )

        # Sum of values in range: 200 + 150 + 175 = 525 sec
        assert result == pytest.approx(525.0 / 60.0)

    def test_without_runtime_sensor_uses_fallback(self, service, base_time):
        """Given no runtime sensor, uses fallback temporal duration."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {}

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=45.0
        )

        assert result == 45.0

    def test_with_single_measurement_in_range(self, service, base_time):
        """Given single on_time_sec measurement in range, uses that value."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {
            HistoricalDataKey.HEATING_RUNTIME_SECONDS: [
                m(base_time + timedelta(minutes=30), 600.0),  # 600 sec at 30min mark
            ]
        }

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=60.0
        )

        assert result == pytest.approx(600.0 / 60.0)  # 10 minutes

    def test_with_zero_sum_uses_fallback(self, service, base_time):
        """Given measurements with zero/invalid values, uses fallback."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {
            HistoricalDataKey.HEATING_RUNTIME_SECONDS: [
                m(base_time, 0.0),  # Zero on_time
                m(base_time + timedelta(minutes=30), "invalid"),  # Invalid type
            ]
        }

        result = service._compute_runtime_minutes(
            data, start_time, end_time, fallback_duration_minutes=50.0
        )

        assert result == 50.0


class TestComputeTariffBreakdown:
    """Tests for _compute_tariff_breakdown helper."""

    def test_with_single_tariff_returns_one_detail(self, service, base_time):
        """Given single tariff price throughout, returns one TariffPeriodDetail."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        tariff_history = [
            m(start_time, 0.15),  # 0.15 EUR/kWh
        ]
        energy_history = [
            m(start_time, 10.0),
            m(end_time, 12.0),  # 2 kWh consumed
        ]
        runtime_history = []

        cost, details = service._compute_tariff_breakdown(
            tariff_history,
            energy_history,
            runtime_history,
            start_time,
            end_time,
            fallback_energy_kwh=0.0,
        )

        assert cost == pytest.approx(0.30)  # 2 kWh * 0.15 EUR/kWh
        assert len(details) == 1
        assert details[0].tariff_price_eur_per_kwh == 0.15
        assert details[0].energy_kwh == pytest.approx(2.0)
        assert details[0].cost_euro == pytest.approx(0.30)

    def test_with_multiple_tariffs_segments_correctly(self, service, base_time):
        """Given tariff price changes, segments cycle and computes each period."""
        start_time = base_time
        mid_time = base_time + timedelta(minutes=30)
        end_time = base_time + timedelta(hours=1)

        tariff_history = [
            m(start_time, 0.10),  # 0.10 EUR/kWh
            m(mid_time, 0.20),  # Price change at 30min
        ]
        energy_history = [
            m(start_time, 10.0),
            m(mid_time, 11.0),  # 1 kWh in first half
            m(end_time, 13.0),  # 2 kWh in second half
        ]
        runtime_history = []

        cost, details = service._compute_tariff_breakdown(
            tariff_history,
            energy_history,
            runtime_history,
            start_time,
            end_time,
            fallback_energy_kwh=0.0,
        )

        assert len(details) == 2
        # First segment: 1 kWh @ 0.10 EUR/kWh = 0.10 EUR
        assert details[0].tariff_price_eur_per_kwh == 0.10
        assert details[0].energy_kwh == pytest.approx(1.0)
        assert details[0].cost_euro == pytest.approx(0.10)
        # Second segment: 2 kWh @ 0.20 EUR/kWh = 0.40 EUR
        assert details[1].tariff_price_eur_per_kwh == 0.20
        assert details[1].energy_kwh == pytest.approx(2.0)
        assert details[1].cost_euro == pytest.approx(0.40)
        # Total cost
        assert cost == pytest.approx(0.50)

    def test_with_runtime_sensor_sums_ontime_in_segment(self, service, base_time):
        """Given runtime sensor with non-cumulative on_time_sec, sums values in segment."""
        start_time = base_time
        mid_time = base_time + timedelta(minutes=30)
        end_time = base_time + timedelta(hours=1)
        tariff_history = [
            m(start_time, 0.15),  # Single tariff throughout
        ]
        energy_history = [
            m(start_time, 10.0),
            m(end_time, 12.0),  # 2 kWh total
        ]
        runtime_history = [
            m(start_time, 600.0),  # 600 sec on_time at start
            m(mid_time, 800.0),  # 800 sec on_time at mid
            m(end_time, 700.0),  # 700 sec on_time at end (not included in segment)
        ]

        cost, details = service._compute_tariff_breakdown(
            tariff_history,
            energy_history,
            runtime_history,
            start_time,
            end_time,
            fallback_energy_kwh=0.0,
        )

        assert len(details) == 1
        # Sum of on_time_sec in [start_time, end_time): 600 + 800 = 1400 sec
        # (end_time value is excluded as segment is a <= t < b)
        assert details[0].heating_duration_minutes == pytest.approx(1400.0 / 60.0)

    def test_without_tariff_or_energy_returns_empty(self, service, base_time):
        """Given missing tariff or energy data, returns (0.0, [])."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)

        # Missing tariff
        cost1, details1 = service._compute_tariff_breakdown(
            [], [m(start_time, 10.0)], [], start_time, end_time, fallback_energy_kwh=0.0
        )
        assert cost1 == 0.0
        assert details1 == []

        # Missing energy
        cost2, details2 = service._compute_tariff_breakdown(
            [m(start_time, 0.15)], [], [], start_time, end_time, fallback_energy_kwh=0.0
        )
        assert cost2 == 0.0
        assert details2 == []


class TestValidateCriticalData:
    """Tests for _validate_critical_data helper."""

    def test_with_all_required_keys_succeeds(self, service):
        """Given dataset with all critical keys, does not raise."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [m(datetime.now(), 20.0)],
                HistoricalDataKey.TARGET_TEMP: [m(datetime.now(), 21.0)],
                HistoricalDataKey.HEATING_STATE: [m(datetime.now(), "heat")],
            }
        )

        # Should not raise
        service._validate_critical_data(dataset)

    def test_with_missing_indoor_temp_raises(self, service):
        """Given missing INDOOR_TEMP, raises ValueError."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.TARGET_TEMP: [m(datetime.now(), 21.0)],
                HistoricalDataKey.HEATING_STATE: [m(datetime.now(), "heat")],
            }
        )

        with pytest.raises(
            ValueError, match="Missing critical historical data for key: indoor_temp"
        ):
            service._validate_critical_data(dataset)

    def test_with_missing_heating_state_raises(self, service):
        """Given missing HEATING_STATE, raises ValueError."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [m(datetime.now(), 20.0)],
                HistoricalDataKey.TARGET_TEMP: [m(datetime.now(), 21.0)],
            }
        )

        with pytest.raises(
            ValueError, match="Missing critical historical data for key: heating_state"
        ):
            service._validate_critical_data(dataset)


class TestGetTemperaturesAt:
    """Tests for _get_temperatures_at helper."""

    def test_with_both_temps_available_returns_tuple(self, service, base_time):
        """Given both temperatures available, returns (indoor, target)."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [m(base_time, 19.5)],
                HistoricalDataKey.TARGET_TEMP: [m(base_time, 21.0)],
            }
        )

        indoor, target = service._get_temperatures_at(dataset, base_time)

        assert indoor == 19.5
        assert target == 21.0

    def test_with_missing_indoor_returns_none(self, service, base_time):
        """Given missing indoor temp, returns (None, target)."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [],
                HistoricalDataKey.TARGET_TEMP: [m(base_time, 21.0)],
            }
        )

        indoor, target = service._get_temperatures_at(dataset, base_time)

        assert indoor is None
        assert target == 21.0

    def test_with_missing_target_returns_none(self, service, base_time):
        """Given missing target temp, returns (indoor, None)."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [m(base_time, 19.5)],
                HistoricalDataKey.TARGET_TEMP: [],
            }
        )

        indoor, target = service._get_temperatures_at(dataset, base_time)

        assert indoor == 19.5
        assert target is None


class TestShouldStartCycle:
    """Tests for _should_start_cycle helper."""

    def test_with_all_conditions_met_returns_true(self, service):
        """Given mode_on=True, action_active=True, temp below target, returns True."""
        result = service._should_start_cycle(
            mode_on=True,
            action_active=True,
            indoor_temp=19.0,
            target_temp=21.0,  # delta = 2.0 > 0.5 threshold
        )

        assert result is True

    def test_with_mode_off_returns_false(self, service):
        """Given mode_on=False (even with other conditions met), returns False."""
        result = service._should_start_cycle(
            mode_on=False,
            action_active=True,
            indoor_temp=19.0,
            target_temp=21.0,
        )

        assert result is False

    def test_with_action_inactive_returns_false(self, service):
        """Given action_active=False, returns False."""
        result = service._should_start_cycle(
            mode_on=True,
            action_active=False,
            indoor_temp=19.0,
            target_temp=21.0,
        )

        assert result is False

    def test_with_temp_within_threshold_returns_false(self, service):
        """Given temperature within threshold of target, returns False."""
        result = service._should_start_cycle(
            mode_on=True,
            action_active=True,
            indoor_temp=20.8,
            target_temp=21.0,  # delta = 0.2 < 0.5 threshold
        )

        assert result is False

    def test_with_missing_temps_returns_false(self, service):
        """Given None temperatures, returns False."""
        result = service._should_start_cycle(
            mode_on=True,
            action_active=True,
            indoor_temp=None,
            target_temp=21.0,
        )

        assert result is False


class TestShouldEndCycle:
    """Tests for _should_end_cycle helper."""

    def test_with_mode_off_returns_true_with_reason(self, service):
        """Given mode_on=False, returns (True, 'mode_disabled')."""
        ended, reason = service._should_end_cycle(
            mode_on=False,
            indoor_temp=19.0,
            target_temp=21.0,
        )

        assert ended is True
        assert reason == "mode_disabled"

    def test_with_target_reached_returns_true(self, service):
        """Given indoor >= target - threshold, returns (True, 'target_reached_or_within_threshold')."""
        ended, reason = service._should_end_cycle(
            mode_on=True,
            indoor_temp=20.8,  # 21.0 - 0.5 = 20.5, so 20.8 >= 20.5
            target_temp=21.0,
        )

        assert ended is True
        assert reason == "target_reached_or_within_threshold"

    def test_with_cycle_ongoing_returns_false(self, service):
        """Given mode_on=True and temp below target, returns (False, '')."""
        ended, reason = service._should_end_cycle(
            mode_on=True,
            indoor_temp=19.0,
            target_temp=21.0,
        )

        assert ended is False
        assert reason == ""

    def test_with_missing_temps_continues(self, service):
        """Given None temperatures (but mode_on), returns (False, '')."""
        ended, reason = service._should_end_cycle(
            mode_on=True,
            indoor_temp=None,
            target_temp=21.0,
        )

        assert ended is False
        assert reason == ""


class TestCalculateDeadTimeCycle:
    """Regression tests for _calculate_dead_time_cycle() method (Issue #62).

    These tests expose coverage gaps in dead time calculation.
    They FAIL with current code to demonstrate missing functionality.
    """

    def test_calculate_dead_time_cycle_detects_threshold(self, service, base_time):
        """Test that dead time is calculated when temp change meets threshold.

        GIVEN: History data with temp rising from 18.0°C to 18.15°C after 5 minutes
        WHEN: _calculate_dead_time_cycle() called with threshold=0.1
        THEN: Should return ~5 minutes

        This test FAILS if _calculate_dead_time_cycle is not properly implemented
        or if temp change detection is broken.
        """
        start_time = base_time
        start_temp = 18.0

        # History shows temp rising to 18.15 at 5 minute mark
        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=5), 18.15),
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Should detect the 0.15°C change (exceeds 0.1 threshold)
        assert result is not None, "Dead time should be detected for temp change >= threshold"
        assert result == pytest.approx(5.0, abs=0.1)

    def test_calculate_dead_time_cycle_returns_minutes(self, service, base_time):
        """Test that duration is correctly converted to minutes.

        GIVEN: Temp changes 0.1°C at exactly 3min 30sec after cycle start
        THEN: Should return 3.5 minutes (not seconds or hours)

        This test FAILS if the method returns seconds instead of minutes,
        or if time conversion is incorrect.
        """
        start_time = base_time
        start_temp = 18.0

        # Temp change after exactly 3:30 (210 seconds)
        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=3, seconds=30), 18.1),
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Expected: 210 seconds / 60 = 3.5 minutes
        assert result is not None
        assert result == pytest.approx(3.5, abs=0.01)

    def test_calculate_dead_time_cycle_below_threshold_returns_none(self, service, base_time):
        """Test that None is returned if temp change is below threshold.

        GIVEN: History shows only 0.05°C temp change (below 0.1 threshold)
        WHEN: Called with threshold=0.1
        THEN: Should return None

        This test FAILS if the threshold check is not implemented correctly.
        """
        start_time = base_time
        start_temp = 18.0

        # Only 0.05°C change (below 0.1 threshold)
        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=5), 18.05),
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # No temp change >= threshold, should return None
        assert result is None, "Should return None when temp change < threshold"

    def test_calculate_dead_time_cycle_missing_history_returns_none(self, service, base_time):
        """Test that None is returned if indoor temp history empty.

        GIVEN: HistoricalDataSet with empty INDOOR_TEMP list
        WHEN: _calculate_dead_time_cycle() called
        THEN: Should return None

        This test FAILS if the method doesn't handle missing history gracefully.
        """
        start_time = base_time
        start_temp = 18.0

        # Empty indoor temp history
        data = {HistoricalDataKey.INDOOR_TEMP: []}
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        assert result is None, "Should return None when history is empty"

    @pytest.mark.parametrize(
        "threshold,expected_detected",
        [
            (0.2, True),  # 0.25°C change >= 0.2 threshold
            (0.3, False),  # 0.25°C change < 0.3 threshold
            (0.25, True),  # 0.25°C change >= 0.25 threshold (boundary)
        ],
    )
    def test_calculate_dead_time_cycle_custom_threshold(
        self, service, base_time, threshold, expected_detected
    ):
        """Test that custom temp_change_threshold parameter is respected.

        GIVEN: History with 0.25°C temp change
        WHEN: Called with different threshold values
        THEN: Should detect change only when it meets the threshold

        This test FAILS if the threshold parameter is not properly applied.
        """
        start_time = base_time
        start_temp = 18.0

        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=5), 18.25),
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=threshold,
        )

        if expected_detected:
            assert result is not None, f"Should detect change when {0.25} >= {threshold}"
            assert result == pytest.approx(5.0, abs=0.1)
        else:
            assert result is None, f"Should NOT detect when {0.25} < {threshold}"

    def test_calculate_dead_time_cycle_first_measurement_after_start(self, service, base_time):
        """Test that dead time uses first measurement AFTER cycle start time.

        GIVEN: History has measurements AT start_time and AFTER start_time
        WHEN: _calculate_dead_time_cycle() called
        THEN: Should use first measurement AFTER start_time (ignoring start_time itself)

        This test FAILS if the method includes measurements at start_time,
        resulting in zero or incorrect dead time.
        """
        start_time = base_time
        start_temp = 18.0

        # Measurement AT start_time should be ignored
        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),  # At start (should be skipped)
                m(
                    start_time + timedelta(seconds=1), 18.05
                ),  # After start (should also be skipped, temp below threshold)
                m(start_time + timedelta(minutes=2), 18.12),  # After start, meets threshold
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Should return dead time to first measurement meeting threshold (~2 minutes)
        assert result is not None
        assert result == pytest.approx(2.0, abs=0.1)

    def test_calculate_dead_time_cycle_negative_temp_change(self, service, base_time):
        """Test that temperature decrease returns None (dead time only on heating rise).

        GIVEN: History shows temperature DECREASING by 0.15°C
        WHEN: _calculate_dead_time_cycle() called with temp_change_threshold=0.1
        THEN: Should return None (dead time cannot be determined from cooling)

        Dead time is the period before heating starts to warm the room.
        If temperature drops, it's not heating - cannot measure dead time.
        Threshold only applies to positive temperature changes.

        This test FAILS if the method uses abs() for threshold check.
        """
        start_time = base_time
        start_temp = 18.0

        # Temp decreases (e.g., cycle end or measurement artifact - NOT heating)
        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=3), 17.85),  # 0.15°C decrease
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Temperature decreased, cannot determine dead time - must return None
        assert result is None, "Should return None when temperature decreases (not heating)"

    def test_calculate_dead_time_cycle_multiple_measurements(self, service, base_time):
        """Test that dead time picks first measurement meeting threshold from multiple measurements.

        GIVEN: History with multiple measurements, first one doesn't meet threshold,
               second one does
        WHEN: _calculate_dead_time_cycle() called
        THEN: Should return dead time based on FIRST measurement meeting threshold

        This test FAILS if the method doesn't iterate through all measurements properly.
        """
        start_time = base_time
        start_temp = 18.0

        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=1), 18.05),  # 0.05°C < 0.1 threshold
                m(start_time + timedelta(minutes=2), 18.08),  # 0.08°C < 0.1 threshold
                m(start_time + timedelta(minutes=3), 18.15),  # 0.15°C >= 0.1 threshold ✓
                m(start_time + timedelta(minutes=4), 18.50),  # 0.50°C (after first match)
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Should return dead time to first measurement meeting threshold (3 minutes)
        assert result is not None
        assert result == pytest.approx(3.0, abs=0.1)

    def test_calculate_dead_time_cycle_handles_invalid_temp_values(self, service, base_time):
        """Test that invalid temperature values are skipped gracefully.

        GIVEN: History with some invalid (non-numeric) temperature values
        WHEN: _calculate_dead_time_cycle() called
        THEN: Should skip invalid values and continue to find valid ones

        This test FAILS if the method crashes or doesn't skip non-numeric values.
        """
        start_time = base_time
        start_temp = 18.0

        data = {
            HistoricalDataKey.INDOOR_TEMP: [
                m(start_time, start_temp),
                m(start_time + timedelta(minutes=1), "invalid"),  # Non-numeric
                m(start_time + timedelta(minutes=2), None),  # None value
                m(start_time + timedelta(minutes=3), 18.15),  # Valid, meets threshold
            ]
        }
        dataset = HistoricalDataSet(data)

        result = service._calculate_dead_time_cycle(
            start_time=start_time,
            start_temp=start_temp,
            history_data_set=dataset,
            temp_change_threshold=0.1,
        )

        # Should skip invalid values and return dead time from valid measurement
        assert result is not None
        assert result == pytest.approx(3.0, abs=0.1)
