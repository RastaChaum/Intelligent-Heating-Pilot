"""pytest-bdd step definitions for HASensorDataReader BDD scenarios.

Implements GIVEN/WHEN/THEN steps for testing sensor historical data access
with mandatory RecorderAccessQueue serialization.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.interfaces.historical_data_adapter_interface import (
    IHistoricalDataAdapter,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.sensor_data_reader import (
    HASensorDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

# Load all scenarios from sensor_data_reader.feature
scenarios("sensor_data_reader.feature")


@pytest.fixture
def sensor_context():
    """Shared context for sensor data reader BDD scenarios."""
    return {}


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.states.get = Mock(return_value=None)
    return hass


@pytest.fixture
def recorder_queue():
    """Create a RecorderAccessQueue."""
    return RecorderAccessQueue()


# ------------------------------------------------------------------
# Background steps
# ------------------------------------------------------------------

@given("a Home Assistant instance is running")
def ha_instance_running(sensor_context, mock_hass):
    """GIVEN: A Home Assistant instance is running."""
    sensor_context["hass"] = mock_hass


@given("a RecorderAccessQueue is available")
def recorder_queue_available(sensor_context, recorder_queue):
    """GIVEN: A RecorderAccessQueue is available."""
    sensor_context["recorder_queue"] = recorder_queue


@given(parsers.parse('a sensor entity "{entity_id}" exists'))
def sensor_entity_exists(sensor_context, entity_id):
    """GIVEN: A sensor entity exists in Home Assistant."""
    sensor_context["entity_id"] = entity_id


# ------------------------------------------------------------------
# Scenario: HASensorDataReader requires RecorderQueue
# ------------------------------------------------------------------

@when("I create a HASensorDataReader with RecorderQueue")
def create_sensor_reader(sensor_context):
    """WHEN: Create a HASensorDataReader with RecorderQueue."""
    reader = HASensorDataReader(
        sensor_context["hass"],
        sensor_context["recorder_queue"],
    )
    sensor_context["reader"] = reader


@then("it should be successfully instantiated")
def successfully_instantiated(sensor_context):
    """THEN: Reader is successfully instantiated."""
    assert sensor_context["reader"] is not None


@then("it should implement IHistoricalDataAdapter interface")
def implements_historical(sensor_context):
    """THEN: Reader implements IHistoricalDataAdapter."""
    assert isinstance(sensor_context["reader"], IHistoricalDataAdapter)


# ------------------------------------------------------------------
# Scenario: Historical data fetch uses RecorderQueue
# ------------------------------------------------------------------

@given("I have a HASensorDataReader with RecorderQueue")
def have_sensor_reader(sensor_context, mock_hass, recorder_queue):
    """GIVEN: A HASensorDataReader with RecorderQueue is ready."""
    reader = HASensorDataReader(mock_hass, recorder_queue)
    sensor_context["reader"] = reader
    sensor_context["hass"] = mock_hass
    sensor_context["recorder_queue"] = recorder_queue


@when("I call fetch_historical_data for outdoor temperature")
def call_fetch_sensor_historical(sensor_context):
    """WHEN: Call fetch_historical_data for outdoor temperature."""
    from datetime import datetime

    from custom_components.intelligent_heating_pilot.domain.value_objects import HistoricalDataKey

    reader = sensor_context["reader"]

    # Mock _fetch_history
    async def mock_fetch(entity_id, start, end):
        return [
            {
                "entity_id": entity_id,
                "state": "5.2",
                "attributes": {},
                "last_changed": "2024-01-15T12:00:00",
            }
        ]

    reader._fetch_history = mock_fetch

    result = asyncio.get_event_loop().run_until_complete(
        reader.fetch_historical_data(
            sensor_context.get("entity_id", "sensor.outdoor_temperature"),
            HistoricalDataKey.OUTDOOR_TEMP,
            datetime(2024, 1, 15, 12, 0),
            datetime(2024, 1, 15, 13, 0),
        )
    )

    sensor_context["fetch_result"] = result
    sensor_context["fetch_completed"] = True


@then("the RecorderQueue lock should be acquired")
def lock_acquired(sensor_context):
    """THEN: RecorderQueue lock was acquired during fetch."""
    assert sensor_context["reader"]._recorder_queue is sensor_context["recorder_queue"]


@then("the lock should be released after data fetch completes")
def lock_released(sensor_context):
    """THEN: Lock is released after fetch."""
    assert not sensor_context["recorder_queue"].lock.locked()


@then("historical data should be returned")
def historical_data_returned(sensor_context):
    """THEN: Historical data was returned."""
    assert sensor_context.get("fetch_completed") is True


# ------------------------------------------------------------------
# Scenario: RecorderQueue is mandatory
# ------------------------------------------------------------------

@when("I try to create a HASensorDataReader without RecorderQueue")
def create_sensor_without_queue(sensor_context, mock_hass):
    """WHEN: Try to create without RecorderQueue."""
    try:
        HASensorDataReader(mock_hass)  # type: ignore[call-arg]
        sensor_context["error"] = None
    except TypeError as e:
        sensor_context["error"] = e


@then("a TypeError should be raised")
def type_error_raised(sensor_context):
    """THEN: A TypeError should be raised."""
    assert sensor_context.get("error") is not None
    assert isinstance(sensor_context["error"], TypeError)


@then("the error should indicate missing required parameter")
def error_indicates_missing_param(sensor_context):
    """THEN: Error indicates missing required parameter."""
    assert "recorder_queue" in str(sensor_context["error"])


# ------------------------------------------------------------------
# Scenario: Multiple readers share the same RecorderQueue
# ------------------------------------------------------------------

@given("I have a RecorderQueue instance")
def have_queue_instance(sensor_context, recorder_queue):
    """GIVEN: A RecorderQueue instance."""
    sensor_context["recorder_queue"] = recorder_queue


@when("I create multiple HASensorDataReader instances with the same queue")
def create_multiple_readers(sensor_context, mock_hass):
    """WHEN: Create multiple readers sharing the same queue."""
    rq = sensor_context["recorder_queue"]
    reader1 = HASensorDataReader(mock_hass, rq)
    reader2 = HASensorDataReader(mock_hass, rq)
    sensor_context["reader1"] = reader1
    sensor_context["reader2"] = reader2


@then("all readers should use the same RecorderQueue instance")
def readers_share_queue(sensor_context):
    """THEN: All readers share the same RecorderQueue."""
    assert sensor_context["reader1"]._recorder_queue is sensor_context["reader2"]._recorder_queue


@then("concurrent fetch operations should be serialized")
def concurrent_serialized(sensor_context):
    """THEN: Concurrent fetch operations are serialized via the shared lock."""
    rq = sensor_context["recorder_queue"]
    assert sensor_context["reader1"]._recorder_queue.lock is rq.lock
    assert sensor_context["reader2"]._recorder_queue.lock is rq.lock
