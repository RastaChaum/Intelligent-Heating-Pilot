"""Integration tests for WeatherDataAdapter using real Home Assistant recorder.

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

from custom_components.intelligent_heating_pilot.infrastructure.adapters.weather_data_adapter import (
    WeatherDataAdapter,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
)


@pytest.mark.usefixtures("recorder_mock")
async def test_weather_adapter_fetch_real_outdoor_temp_history(hass):
    """Test WeatherDataAdapter fetches outdoor temperature from real recorded states."""
    entity_id = "weather.home"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record real states via hass.states.async_set
    # Change state value each time to ensure get_significant_states captures them
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        hass.states.async_set(
            entity_id,
            "sunny",  # Different weather conditions for significance
            {
                "temperature": 12.5,
                "humidity": 65,
                "cloud_coverage": 10,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        hass.states.async_set(
            entity_id,
            "partlycloudy",  # State changed
            {
                "temperature": 13.2,
                "humidity": 68,
                "cloud_coverage": 40,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "cloudy",  # State changed again
            {
                "temperature": 14.0,
                "humidity": 70,
                "cloud_coverage": 80,
            },
        )
        await async_wait_recording_done(hass)

    # Verify recorder has the states
    hist = get_significant_states(hass, start, now, [entity_id])
    assert entity_id in hist
    # get_significant_states filters (real HA behavior)
    assert len(hist[entity_id]) >= 2

    # Test adapter fetches and converts correctly from real recorder data
    adapter = WeatherDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.OUTDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.OUTDOOR_TEMP)
    assert measurements is not None
    assert len(measurements) >= 2
    # Verify first value is correct (always recorded)
    assert measurements[0].value == pytest.approx(12.5)
    # Verify all values are in expected range
    assert all(12.0 <= m.value <= 15.0 for m in measurements)
    # Verify attributes are preserved from real HA states
    assert measurements[0].attributes["humidity"] == 65
    assert measurements[0].entity_id == entity_id


@pytest.mark.usefixtures("recorder_mock")
async def test_weather_adapter_fetch_real_outdoor_humidity_history(hass):
    """Test WeatherDataAdapter fetches outdoor humidity from real recorded states."""
    entity_id = "weather.forecast"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with changing humidity attribute
    with freeze_time(now - timedelta(minutes=20)) as freezer:
        hass.states.async_set(
            entity_id,
            "rainy",  # Different states
            {
                "temperature": 10.0,
                "humidity": 85,
                "cloud_coverage": 100,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=10))
        hass.states.async_set(
            entity_id,
            "partlycloudy",  # State changed
            {
                "temperature": 11.5,
                "humidity": 75,
                "cloud_coverage": 60,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "sunny",  # State changed again
            {
                "temperature": 13.0,
                "humidity": 60,
                "cloud_coverage": 20,
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter extraction from real recorder data
    adapter = WeatherDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.OUTDOOR_HUMIDITY,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.OUTDOOR_HUMIDITY)
    assert measurements is not None
    # get_significant_states may filter some states (real HA behavior)
    assert len(measurements) >= 2
    # Verify first humidity level (always recorded)
    assert measurements[0].value == pytest.approx(85.0)
    # Verify all values are in expected range
    assert all(0 <= m.value <= 100 for m in measurements)


@pytest.mark.usefixtures("recorder_mock")
async def test_weather_adapter_fetch_real_cloud_coverage_history(hass):
    """Test WeatherDataAdapter fetches cloud coverage from real recorded states."""
    entity_id = "weather.local"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with changing cloud_coverage attribute
    with freeze_time(now - timedelta(minutes=30)) as freezer:
        hass.states.async_set(
            entity_id,
            "sunny",  # Different states
            {
                "temperature": 15.0,
                "humidity": 50,
                "cloud_coverage": 5,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=15))
        hass.states.async_set(
            entity_id,
            "partlycloudy",  # State changed
            {
                "temperature": 14.5,
                "humidity": 55,
                "cloud_coverage": 50,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "cloudy",  # State changed again
            {
                "temperature": 14.0,
                "humidity": 60,
                "cloud_coverage": 95,
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter extraction of cloud_coverage from real recorder data
    adapter = WeatherDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.CLOUD_COVERAGE,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.CLOUD_COVERAGE)
    assert measurements is not None
    # get_significant_states may filter some states (real HA behavior)
    assert len(measurements) >= 2
    # Verify first cloud coverage value (always recorded)
    assert measurements[0].value == pytest.approx(5.0)
    # Verify all values are in expected range (0-100%)
    assert all(0 <= m.value <= 100 for m in measurements)


@pytest.mark.usefixtures("recorder_mock")
async def test_weather_adapter_handles_missing_attributes_in_real_states(hass):
    """Test adapter handles weather states where expected attributes might be missing."""
    entity_id = "weather.partial"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with some missing attributes (edge case)
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        # State with all attributes
        hass.states.async_set(
            entity_id,
            "sunny",
            {
                "temperature": 16.0,
                "humidity": 45,
                "cloud_coverage": 10,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        # State missing temperature attribute
        hass.states.async_set(
            entity_id,
            "partlycloudy",  # State changed
            {
                "humidity": 50,
                "cloud_coverage": 40,
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        # State with temperature again
        hass.states.async_set(
            entity_id,
            "cloudy",  # State changed again
            {
                "temperature": 15.0,
                "humidity": 55,
                "cloud_coverage": 70,
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter only extracts valid measurements from real recorder data
    adapter = WeatherDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.OUTDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.OUTDOOR_TEMP)
    assert measurements is not None
    # Should get 1-2 measurements (middle state has no temperature, plus get_significant_states filtering)
    assert len(measurements) >= 1
    # Verify valid measurements have correct values
    assert measurements[0].value == pytest.approx(16.0)
    if len(measurements) >= 2:
        # Second valid measurement should be from the last state
        assert measurements[-1].value == pytest.approx(15.0)
