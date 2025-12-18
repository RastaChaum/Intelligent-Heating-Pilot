"""Integration tests for SensorDataAdapter using real Home Assistant recorder.

These tests use real HA state recording via hass.states.async_set + recorder,
not manually constructed State objects, to ensure adapter behavior matches
actual Home Assistant data structures.
"""
from datetime import timedelta

import pytest
from freezegun import freeze_time

from homeassistant.util import dt as dt_util
from homeassistant.components.recorder.history import get_significant_states
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.intelligent_heating_pilot.infrastructure.adapters.sensor_data_adapter import (
    SensorDataAdapter,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
)


@pytest.mark.usefixtures("recorder_mock")
async def test_sensor_adapter_fetch_real_sensor_value_history(hass):
    """Test SensorDataAdapter fetches sensor values from real recorded states."""
    entity_id = "sensor.temperature_bedroom"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record real states via hass.states.async_set
    # Change state value each time to ensure get_significant_states captures them
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        hass.states.async_set(
            entity_id,
            "18.5",  # State is the sensor value (different values for significance)
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        hass.states.async_set(
            entity_id,
            "19.2",  # State changed
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "19.8",  # State changed again
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        await async_wait_recording_done(hass)

    # Verify recorder has the states
    hist = get_significant_states(hass, start, now, [entity_id])
    assert entity_id in hist
    # get_significant_states filters (real HA behavior)
    assert len(hist[entity_id]) >= 2

    # Test adapter fetches and converts correctly from real recorder data
    adapter = SensorDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.INDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.INDOOR_TEMP)
    assert measurements is not None
    assert len(measurements) >= 2
    # Verify first value is correct (always recorded)
    assert measurements[0].value == pytest.approx(18.5)
    # Verify all values are in expected range
    assert all(18.0 <= m.value <= 20.0 for m in measurements)
    # Verify attributes are preserved from real HA states
    assert measurements[0].attributes["unit_of_measurement"] == "°C"
    assert measurements[0].entity_id == entity_id


@pytest.mark.usefixtures("recorder_mock")
async def test_sensor_adapter_fetch_real_battery_level_history(hass):
    """Test SensorDataAdapter fetches battery levels from real recorded states."""
    entity_id = "sensor.temperature_sensor_battery"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with changing battery attribute
    # Change state value each time for significance
    with freeze_time(now - timedelta(minutes=20)) as freezer:
        hass.states.async_set(
            entity_id,
            "100",  # Different state values
            {
                "unit_of_measurement": "%",
                "device_class": "battery",
                "battery_level": 100,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=10))
        hass.states.async_set(
            entity_id,
            "85",  # State changed
            {
                "unit_of_measurement": "%",
                "device_class": "battery",
                "battery_level": 85,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "70",  # State changed again
            {
                "unit_of_measurement": "%",
                "device_class": "battery",
                "battery_level": 70,
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter extraction from real recorder data
    adapter = SensorDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.INDOOR_HUMIDITY,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.INDOOR_HUMIDITY)
    assert measurements is not None
    # get_significant_states may filter some states (real HA behavior)
    assert len(measurements) >= 2
    # Verify first battery level (always recorded)
    assert measurements[0].value == pytest.approx(100.0)
    # Verify all values are in expected range
    assert all(0 <= m.value <= 100 for m in measurements)


@pytest.mark.usefixtures("recorder_mock")
async def test_sensor_adapter_handles_non_numeric_states(hass):
    """Test adapter handles sensors with non-numeric states (should be filtered)."""
    entity_id = "sensor.status_sensor"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with some non-numeric values
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        # Numeric state
        hass.states.async_set(
            entity_id,
            "42.5",
            {
                "unit_of_measurement": "units",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        # Non-numeric state (should be filtered by adapter)
        hass.states.async_set(
            entity_id,
            "unavailable",
            {
                "unit_of_measurement": "units",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        # Numeric state again
        hass.states.async_set(
            entity_id,
            "45.0",
            {
                "unit_of_measurement": "units",
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter only extracts valid numeric measurements
    adapter = SensorDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.INDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.INDOOR_TEMP)
    assert measurements is not None
    # Should get 1-2 numeric measurements (non-numeric state filtered, plus get_significant_states filtering)
    assert len(measurements) >= 1
    # Verify valid measurements have correct numeric values
    assert measurements[0].value == pytest.approx(42.5)
    # All returned values should be numeric
    assert all(isinstance(m.value, (int, float)) for m in measurements)
