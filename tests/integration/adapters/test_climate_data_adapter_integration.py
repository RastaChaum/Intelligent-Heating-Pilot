"""Integration tests for ClimateDataAdapter using real Home Assistant recorder.

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

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
    ClimateDataAdapter,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
)


@pytest.mark.usefixtures("recorder_mock")
async def test_climate_adapter_fetch_real_indoor_temp_history(hass):
    """Test ClimateDataAdapter fetches indoor temperature from real recorded states."""
    entity_id = "climate.living_room"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record real states via hass.states.async_set (like actual climate entities do)
    # Change state value each time to ensure get_significant_states captures them
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        hass.states.async_set(
            entity_id,
            "auto",  # Different state values to trigger significant state changes
            {
                "current_temperature": 19.1,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        hass.states.async_set(
            entity_id,
            "heat",  # State changed
            {
                "current_temperature": 19.6,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "off",  # State changed again
            {
                "current_temperature": 20.2,
                "target_temperature": 21.0,
                "hvac_action": "idle",
            },
        )
        await async_wait_recording_done(hass)

    # Verify recorder has the states
    hist = get_significant_states(hass, start, now, [entity_id])
    assert entity_id in hist
    # get_significant_states filters non-significant states (real HA behavior)
    # We expect 2-3 states depending on filtering
    assert len(hist[entity_id]) >= 2

    # Now test adapter fetches and converts correctly from real recorder data
    adapter = ClimateDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.INDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.INDOOR_TEMP)
    assert measurements is not None
    # Adapter gets what recorder returns (filtered by significance)
    assert len(measurements) >= 2
    # Verify first value is correct (always recorded)
    assert measurements[0].value == pytest.approx(19.1)
    # Verify all values are in expected range
    assert all(19.0 <= m.value <= 21.0 for m in measurements)
    # Verify attributes are preserved from real HA states
    assert measurements[0].attributes["hvac_action"] == "heating"
    assert measurements[0].entity_id == entity_id


@pytest.mark.usefixtures("recorder_mock")
async def test_climate_adapter_fetch_real_target_temp_history(hass):
    """Test ClimateDataAdapter fetches target temperature from real recorded states."""
    entity_id = "climate.bedroom"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with changing target_temperature
    # Change state value each time to ensure significant state changes
    with freeze_time(now - timedelta(minutes=20)) as freezer:
        hass.states.async_set(
            entity_id,
            "auto",  # Different states to trigger significance
            {
                "current_temperature": 18.5,
                "target_temperature": 20.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=10))
        hass.states.async_set(
            entity_id,
            "heat",  # State changed
            {
                "current_temperature": 19.0,
                "target_temperature": 21.5,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "off",  # State changed again
            {
                "current_temperature": 20.0,
                "target_temperature": 22.0,
                "hvac_action": "idle",
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter extraction from real recorder data
    adapter = ClimateDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.TARGET_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.TARGET_TEMP)
    assert measurements is not None
    # get_significant_states may filter some states (real HA behavior)
    assert len(measurements) >= 2
    # Verify first target temperature (always recorded)
    assert measurements[0].value == pytest.approx(20.0)
    # Verify all values are in expected range
    assert all(20.0 <= m.value <= 22.0 for m in measurements)


@pytest.mark.usefixtures("recorder_mock")
async def test_climate_adapter_fetch_real_heating_state_history(hass):
    """Test ClimateDataAdapter fetches hvac_action (heating state) from real recorded states."""
    entity_id = "climate.kitchen"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with changing hvac_action
    # State value already changes (heat → heat → off), but ensure all are different
    with freeze_time(now - timedelta(minutes=30)) as freezer:
        hass.states.async_set(
            entity_id,
            "auto",  # Different state values
            {
                "current_temperature": 19.0,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=15))
        hass.states.async_set(
            entity_id,
            "heat",  # State changed
            {
                "current_temperature": 20.5,
                "target_temperature": 21.0,
                "hvac_action": "idle",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        hass.states.async_set(
            entity_id,
            "off",  # State changed again
            {
                "current_temperature": 20.8,
                "target_temperature": None,
                "hvac_action": "off",
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter extraction of hvac_action from real recorder data
    adapter = ClimateDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.HEATING_STATE,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.HEATING_STATE)
    assert measurements is not None
    # get_significant_states may filter some states (real HA behavior)
    assert len(measurements) >= 2
    # Verify first hvac_action value (always recorded)
    assert measurements[0].value == "heating"
    # Verify all values are valid hvac_action states
    assert all(m.value in ["heating", "idle", "off"] for m in measurements)


@pytest.mark.usefixtures("recorder_mock")
async def test_climate_adapter_handles_missing_attributes_in_real_states(hass):
    """Test adapter handles states where expected attributes might be missing."""
    entity_id = "climate.faulty"
    now = dt_util.utcnow()
    start = now - timedelta(hours=1)
    
    # Record states with some missing attributes (edge case)
    # Change state value each time to ensure significance
    with freeze_time(now - timedelta(minutes=10)) as freezer:
        # State with all attributes
        hass.states.async_set(
            entity_id,
            "auto",  # Different states
            {
                "current_temperature": 19.0,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now - timedelta(minutes=5))
        # State missing current_temperature
        hass.states.async_set(
            entity_id,
            "heat",  # State changed
            {
                "target_temperature": 21.0,
                "hvac_action": "idle",
            },
        )
        await async_wait_recording_done(hass)
        
        freezer.move_to(now)
        # State with current_temperature again
        hass.states.async_set(
            entity_id,
            "off",  # State changed again
            {
                "current_temperature": 20.0,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
        )
        await async_wait_recording_done(hass)

    # Test adapter only extracts valid measurements from real recorder data
    adapter = ClimateDataAdapter(hass)
    dataset = await adapter.fetch_historical_data(
        entity_id=entity_id,
        data_key=HistoricalDataKey.INDOOR_TEMP,
        start_time=start,
        end_time=now,
    )

    measurements = dataset.data.get(HistoricalDataKey.INDOOR_TEMP)
    assert measurements is not None
    # Should get 1-2 measurements (middle state has no current_temperature, plus get_significant_states filtering)
    assert len(measurements) >= 1
    # Verify valid measurements have correct values
    assert measurements[0].value == pytest.approx(19.0)
    if len(measurements) >= 2:
        assert measurements[-1].value == pytest.approx(20.0)
