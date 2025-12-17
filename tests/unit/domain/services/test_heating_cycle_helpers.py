"""Unit tests for HeatingCycleService helper methods extracted during refactoring."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add domain to path WITHOUT loading infrastructure layer
DOMAIN_PATH = Path(__file__).parent.parent.parent.parent.parent / "custom_components" / "intelligent_heating_pilot" / "domain"
sys.path.insert(0, str(DOMAIN_PATH.parent))

from domain.services.heating_cycle_service import HeatingCycleService
from domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)
from domain.value_objects.heating import TariffPeriodDetail


def m(timestamp: datetime, value: float | str | bool, device_id: str = "test.device") -> HistoricalMeasurement:
    """Helper to create HistoricalMeasurement with empty attributes."""
    return HistoricalMeasurement(timestamp, value, {}, device_id)


@pytest.fixture
def service():
    """Create HeatingCycleService instance for testing."""
    return HeatingCycleService(
        temp_delta_threshold=0.5,
        cycle_split_duration_minutes=None,
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
                m(mid1, 180.0),        # 180 sec on_time at 10:05
                m(mid2, 240.0),        # 240 sec on_time at 10:10
                m(end_time, 150.0),    # 150 sec on_time at 10:15 (reset happened)
            ]
        }

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=60.0)

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

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=45.0)

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

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=60.0)

        # Sum of values in range: 200 + 150 + 175 = 525 sec
        assert result == pytest.approx(525.0 / 60.0)

    def test_without_runtime_sensor_uses_fallback(self, service, base_time):
        """Given no runtime sensor, uses fallback temporal duration."""
        start_time = base_time
        end_time = base_time + timedelta(hours=1)
        data = {}

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=45.0)

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

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=60.0)

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

        result = service._compute_runtime_minutes(data, start_time, end_time, fallback_duration_minutes=50.0)

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
            tariff_history, energy_history, runtime_history,
            start_time, end_time, fallback_energy_kwh=0.0
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
            m(mid_time, 0.20),   # Price change at 30min
        ]
        energy_history = [
            m(start_time, 10.0),
            m(mid_time, 11.0),  # 1 kWh in first half
            m(end_time, 13.0),  # 2 kWh in second half
        ]
        runtime_history = []

        cost, details = service._compute_tariff_breakdown(
            tariff_history, energy_history, runtime_history,
            start_time, end_time, fallback_energy_kwh=0.0
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
            m(end_time, 12.0),    # 2 kWh total
        ]
        runtime_history = [
            m(start_time, 600.0),    # 600 sec on_time at start
            m(mid_time, 800.0),      # 800 sec on_time at mid
            m(end_time, 700.0),      # 700 sec on_time at end (not included in segment)
        ]

        cost, details = service._compute_tariff_breakdown(
            tariff_history, energy_history, runtime_history,
            start_time, end_time, fallback_energy_kwh=0.0
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
            [], [m(start_time, 10.0)], [],
            start_time, end_time, fallback_energy_kwh=0.0
        )
        assert cost1 == 0.0
        assert details1 == []

        # Missing energy
        cost2, details2 = service._compute_tariff_breakdown(
            [m(start_time, 0.15)], [], [],
            start_time, end_time, fallback_energy_kwh=0.0
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

        with pytest.raises(ValueError, match="Missing critical historical data for key: indoor_temp"):
            service._validate_critical_data(dataset)

    def test_with_missing_heating_state_raises(self, service):
        """Given missing HEATING_STATE, raises ValueError."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [m(datetime.now(), 20.0)],
                HistoricalDataKey.TARGET_TEMP: [m(datetime.now(), 21.0)],
            }
        )

        with pytest.raises(ValueError, match="Missing critical historical data for key: heating_state"):
            service._validate_critical_data(dataset)


class TestGetTemperaturesAt:
    """Tests for _get_temperatures_at helper."""

    def test_with_both_temps_available_returns_tuple(self, service, base_time):
        """Given both temperatures available, returns (indoor, target)."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(base_time, 19.5)
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    m(base_time, 21.0)
                ],
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
                HistoricalDataKey.TARGET_TEMP: [
                    m(base_time, 21.0)
                ],
            }
        )

        indoor, target = service._get_temperatures_at(dataset, base_time)

        assert indoor is None
        assert target == 21.0

    def test_with_missing_target_returns_none(self, service, base_time):
        """Given missing target temp, returns (indoor, None)."""
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(base_time, 19.5)
                ],
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
