"""Integration tests for HeatingCycleService.extract_heating_cycles method."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

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


def m(timestamp: datetime, value: float | str | bool, hvac_action: str | None = None, hvac_mode: str | None = None, device_id: str = "test.device") -> HistoricalMeasurement:
    """Helper to create HistoricalMeasurement with optional climate attributes."""
    attrs = {}
    if hvac_action:
        attrs["hvac_action"] = hvac_action
    if hvac_mode:
        attrs["hvac_mode"] = hvac_mode
    return HistoricalMeasurement(timestamp, value, attrs, device_id)


@pytest.fixture
def service():
    """Create HeatingCycleService for testing."""
    return HeatingCycleService(
        temp_delta_threshold=0.5,
        cycle_split_duration_minutes=None,
        min_cycle_duration_minutes=5,
        max_cycle_duration_minutes=300,
    )


@pytest.fixture
def service_with_splitting():
    """Create HeatingCycleService with cycle splitting enabled."""
    return HeatingCycleService(
        temp_delta_threshold=0.5,
        cycle_split_duration_minutes=30,  # Split cycles longer than 30 minutes
        min_cycle_duration_minutes=5,
        max_cycle_duration_minutes=300,
    )


@pytest.fixture
def base_time():
    """Base timestamp for tests."""
    return datetime(2024, 1, 1, 12, 0, 0)


class TestExtractSingleHeatingCycle:
    """Test extraction of a single complete heating cycle."""

    @pytest.mark.asyncio
    async def test_single_cycle_start_to_end(self, service, base_time):
        """Given a single heating cycle from start to end, extracts one HeatingCycle."""
        # Build timeline: start -> heat for 30 min -> reach target -> stop
        # Threshold is 0.5°C, so cycle ends when indoor >= (target - 0.5)
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)  # Mode ON, heating active, temp below target
        t2 = t0 + timedelta(minutes=25)  # Still heating, temp at 19.2°C (below 19.5 threshold)
        t3 = t0 + timedelta(minutes=35)  # Reached target threshold, heating stops
        t4 = t0 + timedelta(minutes=45)  # After cycle ends

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),      # 20.0 - 19.0 = 1.0 > 0.5 threshold
                    m(t2, 19.2),      # 20.0 - 19.2 = 0.8 > 0.5 threshold, still heating
                    m(t3, 19.6),      # 20.0 - 19.6 = 0.4 < 0.5 threshold -> cycle ends
                    m(t4, 20.1),
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    m(t0, 20.0),
                    m(t1, 20.0),
                    m(t2, 20.0),
                    m(t3, 20.0),
                    m(t4, 20.0),
                ],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START CYCLE
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),
                    m(t3, False, hvac_action="heating", hvac_mode="heat"),  # END CYCLE
                    m(t4, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t4 + timedelta(minutes=5))

        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.start_time == t1
        assert cycle.end_time == t3
        assert cycle.start_temp == pytest.approx(19.0)
        assert cycle.end_temp == pytest.approx(19.6)
        assert cycle.target_temp == 20.0

    @pytest.mark.asyncio
    async def test_cycle_ends_on_mode_disabled(self, service, base_time):
        """Given heating active but mode disabled, cycle ends."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=5)
        t2 = t0 + timedelta(minutes=10)
        t3 = t0 + timedelta(minutes=15)  # Mode disabled even though heating is active

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),  # 19.0 < 20.0 - 0.5, start cycle
                    m(t2, 19.2),  # Still below threshold
                    m(t3, 19.3),  # Still below threshold
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),
                    m(t3, True, hvac_action="heating", hvac_mode="off"),  # Mode disabled -> END
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t3 + timedelta(minutes=5))

        assert len(cycles) == 1
        assert cycles[0].end_time == t3


class TestExtractMultipleCycles:
    """Test extraction of multiple heating cycles with no overlap."""

    @pytest.mark.asyncio
    async def test_two_consecutive_cycles_no_overlap(self, service, base_time):
        """Given two heating cycles in sequence, extracts both without overlap."""
        # Cycle 1: t1-t3 (ends at temperature threshold)
        # Cycle 2: t4-t6 (same logic)
        t0 = base_time
        t1 = t0 + timedelta(minutes=5)
        t2 = t0 + timedelta(minutes=10)
        t3 = t0 + timedelta(minutes=15)  # Cycle 1 ends here
        t4 = t0 + timedelta(minutes=20)
        t5 = t0 + timedelta(minutes=25)
        t6 = t0 + timedelta(minutes=30)
        t7 = t0 + timedelta(minutes=40)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),  # Cycle 1: 19.0 < 20.0 - 0.5, start
                    m(t2, 19.3),  # Cycle 1: still below threshold
                    m(t3, 19.6),  # Cycle 1: 19.6 >= 20.0 - 0.5, END
                    m(t4, 19.0),  # Cool down and re-start
                    m(t5, 19.3),  # Cycle 2: below threshold
                    m(t6, 19.6),  # Cycle 2: 19.6 >= 20.0 - 0.5, END
                    m(t7, 19.7),  # OUT OF CYLE
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3, t4, t5, t6, t7]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # CYCLE 1 START
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),
                    m(t3, False, hvac_action="heating", hvac_mode="heat"),  # CYCLE 1 END (threshold + mode off)
                    m(t4, True, hvac_action="heating", hvac_mode="heat"),  # CYCLE 2 START
                    m(t5, True, hvac_action="heating", hvac_mode="heat"),
                    m(t6, False, hvac_action="heating", hvac_mode="heat"),  # CYCLE 2 END
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t6 + timedelta(minutes=5))

        assert len(cycles) == 2
        assert cycles[0].start_time == t1
        assert cycles[0].end_time == t3
        assert cycles[1].start_time == t4
        assert cycles[1].end_time == t6
        # Verify no overlap
        assert cycles[0].end_time <= cycles[1].start_time

    @pytest.mark.asyncio
    async def test_measurements_not_shared_between_cycles(self, service, base_time):
        """Verify that no HistoricalMeasurement timestamp is shared between adjacent cycles."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)
        t2 = t0 + timedelta(minutes=20)
        t3 = t0 + timedelta(minutes=30)
        t4 = t0 + timedelta(minutes=40)
        t5 = t0 + timedelta(minutes=50)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),  # Cycle 1 starts (19.0 < 20.0 - 0.5)
                    m(t2, 19.2),  # Still in cycle 1
                    m(t3, 19.6),  # Cycle 1 ends (19.6 >= 20.0 - 0.5)
                    m(t4, 18.8),  # Cool down enough for cycle 2 to start
                    m(t5, 19.0),  # Cycle 2: still below threshold
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3, t4, t5]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # CYCLE 1 START
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),
                    m(t3, True, hvac_action="heating", hvac_mode="heat"),  # Still heating when reaching threshold
                    m(t4, True, hvac_action="heating", hvac_mode="heat"),  # CYCLE 2 START (18.8 < 19.5)
                    m(t5, False, hvac_action="off", hvac_mode="heat"),  # CYCLE 2 END
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t5 + timedelta(minutes=5))

        assert len(cycles) == 2
        assert cycles[0].start_time == t1
        assert cycles[0].end_time == t3
        assert cycles[1].start_time == t4
        # Verify no overlap
        assert cycles[0].end_time <= cycles[1].start_time


class TestExtractWithCycleSplitting:
    """Test cycle splitting for ML data augmentation."""

    @pytest.mark.asyncio
    async def test_long_cycle_split_into_subcycles(self, service_with_splitting, base_time):
        """Given cycle longer than split_duration, splits into multiple sub-cycles."""
        # Create a 90-minute cycle that should split into 3 sub-cycles (30 min each)
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)  # Heating starts
        t2 = t0 + timedelta(minutes=40)  # After 30 min of heating
        t3 = t0 + timedelta(minutes=70)  # After 60 min of heating
        t4 = t0 + timedelta(minutes=110)  # After 100 min of heating
        t5 = t0 + timedelta(minutes=190)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 15.0),
                    m(t1, 16.0),
                    m(t2, 17.5),
                    m(t3, 19.0),
                    m(t4, 20.5),
                    m(t5, 20.5),
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3, t4, t5]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"), 
                    m(t2, False, hvac_action="off", hvac_mode="heat"),  # END
                    m(t3, True, hvac_action="heating", hvac_mode="heat"),
                    m(t4, False, hvac_action="off", hvac_mode="heat"),  # END    
                    m(t5, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        cycles = await service_with_splitting.extract_heating_cycles("my_device_id", dataset, t0, t3 + timedelta(minutes=5))

        # With 30-min split duration and ~90 min cycle: should get 3 sub-cycles + 1 remaining
        # or 3 complete + 1 remainder (90 = 3*30 + 10)
        assert len(cycles) == 4 
        # Verify sub-cycles are contiguous and cover the full time range
        total_duration = sum(
            (c.end_time - c.start_time).total_seconds() / 60.0 for c in cycles
        )
        expected_duration = (t4 - t1).total_seconds() / 60.0
        assert total_duration == pytest.approx(expected_duration, rel=0.1)

    @pytest.mark.asyncio
    async def test_short_cycle_not_split(self, service_with_splitting, base_time):
        """Given cycle shorter than split_duration, does not split."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)  # Heating starts
        t2 = t0 + timedelta(minutes=35)  # After 25 min (less than 30-min split threshold)
        t3 = t0 + timedelta(minutes=45)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),
                    m(t2, 20.5),
                    m(t3, 20.5),
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START
                    m(t2, False, hvac_action="off", hvac_mode="heat"),  # END
                    m(t3, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        cycles = await service_with_splitting.extract_heating_cycles("my_device_id", dataset, t0, t3 + timedelta(minutes=5))

        # Should not split (25 min < 30 min threshold)
        assert len(cycles) == 1


class TestExtractEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_unfinished_cycle_at_end(self, service, base_time):
        """Given heating active at end of dataset, includes unfinished cycle."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)
        t2 = t0 + timedelta(minutes=20)  # End of data (still heating)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),  # 19.0 < 20.0 - 0.5, start cycle
                    m(t2, 19.2),  # Still below threshold at end of dataset
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),  # Still active at end
                ],
            }
        )

        end_time = t2 + timedelta(minutes=5)
        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, end_time)

        assert len(cycles) == 1
        assert cycles[0].start_time == t1
        assert cycles[0].end_time == end_time  # Uses dataset end_time

    @pytest.mark.asyncio
    async def test_too_short_cycle_rejected(self, service, base_time):
        """Given cycle shorter than min_cycle_duration, rejects it."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=1)  # Very short cycle
        t2 = t0 + timedelta(minutes=3)
        t3 = t0 + timedelta(minutes=10)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 19.0),
                    m(t2, 19.5),
                    m(t3, 19.5),
                ],
                HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in [t0, t1, t2, t3]],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START
                    m(t2, False, hvac_action="off", hvac_mode="heat"),  # END after 2 min (< 5 min min)
                    m(t3, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t3 + timedelta(minutes=5))

        # Should reject the short cycle (2 min < 5 min minimum)
        assert len(cycles) == 0

    @pytest.mark.asyncio
    async def test_missing_temperature_data_falls_back_to_prior(self, service, base_time):
        """Given missing temperature at some timestamps, falls back to prior measurement."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=5)
        t2 = t0 + timedelta(minutes=10)
        t3 = t0 + timedelta(minutes=15)
        t4 = t0 + timedelta(minutes=20)

        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    # Missing at t1 → _get_value_at_time(t1) returns t0's value (18.0)
                    m(t2, 19.2),  # Temperature updated at t2
                    #m(t3, 19.5),  # At threshold
                    #m(t4, 19.0),  # Below threshold
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    m(t0, 20.0),
                    m(t1, 20.0),
                    m(t2, 20.0),
                    m(t3, 20.0),
                    m(t4, 20.0),
                ],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, False, hvac_action="off", hvac_mode="off"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),  # START
                    m(t2, True, hvac_action="heating", hvac_mode="heat"),  # Continues heating
                    m(t3, True, hvac_action="heating", hvac_mode="heat"),  # At threshold
                    m(t4, False, hvac_action="off", hvac_mode="heat"),  # END
                ],
            }
        )

        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t4 + timedelta(minutes=5))

        # Cycle detection uses closest prior temp when exact timestamp is unavailable.
        # At t1: mode=True, temp=18.0 (from t0 fallback), delta=2.0 > 0.5 → START
        # At t2-t3: continues heating, reaches threshold
        # At t4: mode off → END
        assert len(cycles) == 1
        assert cycles[0].start_time == t1  # Starts at t1 (even with fallback temp)
        assert cycles[0].start_temp == 18.0  # uses t0 temp fallback (18.0)
        assert cycles[0].end_time == t4 + timedelta(minutes=5)  # Ends at t4
        assert cycles[0].end_temp == 19.2  # uses t2 temp fallback (19.2)        

    @pytest.mark.asyncio
    async def test_empty_dataset_raises_error(self, service, base_time):
        """Given dataset without required keys, raises ValueError."""
        dataset = HistoricalDataSet(data={})

        with pytest.raises(ValueError, match="Missing critical historical data"):
            await service.extract_heating_cycles("my_device_id", dataset, base_time, base_time + timedelta(hours=1))

    @pytest.mark.asyncio
    async def test_cycle_split_duration_parameter_override(self, service, base_time):
        """Given cycle_split_duration_minutes parameter, overrides instance setting."""
        t0 = base_time
        t1 = t0 + timedelta(minutes=5)
        t2 = t0 + timedelta(minutes=45)  # 45-min cycle
        t3 = t0 + timedelta(minutes=48)
        
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 18.5),
                    m(t2, 20.4),
                    m(t3, 20.4),
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    m(t0, 20.0),
                    m(t1, 20.0),
                    m(t2, 20.0),
                    m(t3, 20.0),
                ],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, True, hvac_action="heating", hvac_mode="heat"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),
                    m(t2, False, hvac_action="off", hvac_mode="heat"),
                    m(t3, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        # Service without splitting should return 1 cycle
        cycles = await service.extract_heating_cycles("my_device_id", dataset, t0, t3)
        assert len(cycles) == 1

        # Same service with cycle_split_duration_minutes parameter should split the cycle
        cycles_split = await service.extract_heating_cycles(
            "my_device_id", dataset, t0, t3, cycle_split_duration_minutes=15
        )
        # 45-minute cycle split at 15-minute intervals = 3 sub-cycles + 1 remainder of 3 minutes
        assert len(cycles_split) == 3

    @pytest.mark.asyncio
    async def test_explicit_none_split_parameter_uses_instance_default(self, service, base_time):
        """Given cycle_split_duration_minutes=None (legacy cache data), falls back to instance default without errors."""
        # This test ensures backward compatibility with legacy cache entries where split=None
        t0 = base_time
        t1 = t0 + timedelta(minutes=10)
        t2 = t0 + timedelta(minutes=40)
        t3 = t0 + timedelta(minutes=50)
        
        dataset = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    m(t0, 18.0),
                    m(t1, 18.5),
                    m(t2, 20.4),
                    m(t3, 20.4),
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    m(t0, 20.0),
                    m(t1, 20.0),
                    m(t2, 20.0),
                    m(t3, 20.0),
                ],
                HistoricalDataKey.HEATING_STATE: [
                    m(t0, True, hvac_action="heating", hvac_mode="heat"),
                    m(t1, True, hvac_action="heating", hvac_mode="heat"),
                    m(t2, False, hvac_action="off", hvac_mode="heat"),
                    m(t3, False, hvac_action="off", hvac_mode="heat"),
                ],
            }
        )

        # Service with instance default split=None, and explicitly passing None
        # Should not raise TypeError on None > 0 comparison
        cycles = await service.extract_heating_cycles(
            "my_device_id", dataset, t0, t3, cycle_split_duration_minutes=None
        )
        
        # Should return 1 cycle (no splitting since instance default is None)
        assert len(cycles) == 1
        assert cycles[0].start_time == t0
        # Verify no TypeError was raised during extraction