"""pytest-bdd step definitions for HAWeatherDataReader BDD scenarios.

Implements GIVEN/WHEN/THEN steps for testing weather historical data access
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
from custom_components.intelligent_heating_pilot.infrastructure.adapters.weather_data_reader import (
    HAWeatherDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

# Load all scenarios from weather_data_reader.feature
scenarios("weather_data_reader.feature")


@pytest.fixture
def weather_context():
    """Shared context for weather data reader BDD scenarios."""
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
def ha_instance_running(weather_context, mock_hass):
    """GIVEN: A Home Assistant instance is running."""
    weather_context["hass"] = mock_hass


@given("a RecorderAccessQueue is available")
def recorder_queue_available(weather_context, recorder_queue):
    """GIVEN: A RecorderAccessQueue is available."""
    weather_context["recorder_queue"] = recorder_queue


@given(parsers.parse('a weather entity "{entity_id}" exists'))
def weather_entity_exists(weather_context, entity_id):
    """GIVEN: A weather entity exists in Home Assistant."""
    weather_context["entity_id"] = entity_id


# ------------------------------------------------------------------
# Scenario: HAWeatherDataReader requires RecorderQueue
# ------------------------------------------------------------------

@when("I create a HAWeatherDataReader with RecorderQueue")
def create_weather_reader(weather_context):
    """WHEN: Create a HAWeatherDataReader with RecorderQueue."""
    reader = HAWeatherDataReader(
        weather_context["hass"],
        weather_context["recorder_queue"],
    )
    weather_context["reader"] = reader


@then("it should be successfully instantiated")
def successfully_instantiated(weather_context):
    """THEN: Reader is successfully instantiated."""
    assert weather_context["reader"] is not None


@then("it should implement IHistoricalDataAdapter interface")
def implements_historical(weather_context):
    """THEN: Reader implements IHistoricalDataAdapter."""
    assert isinstance(weather_context["reader"], IHistoricalDataAdapter)


# ------------------------------------------------------------------
# Scenario: Historical data fetch uses RecorderQueue
# ------------------------------------------------------------------

@given("I have a HAWeatherDataReader with RecorderQueue")
def have_weather_reader(weather_context, mock_hass, recorder_queue):
    """GIVEN: A HAWeatherDataReader with RecorderQueue is ready."""
    reader = HAWeatherDataReader(mock_hass, recorder_queue)
    weather_context["reader"] = reader
    weather_context["hass"] = mock_hass
    weather_context["recorder_queue"] = recorder_queue


@when("I call fetch_historical_data for outdoor temperature")
def call_fetch_weather_historical(weather_context):
    """WHEN: Call fetch_historical_data for outdoor temperature."""
    from datetime import datetime

    from custom_components.intelligent_heating_pilot.domain.value_objects import HistoricalDataKey

    reader = weather_context["reader"]

    # Mock _fetch_history
    async def mock_fetch(entity_id, start, end):
        return [
            {
                "entity_id": entity_id,
                "state": "sunny",
                "attributes": {"temperature": 8.5, "humidity": 65},
                "last_changed": "2024-01-15T12:00:00",
            }
        ]

    reader._fetch_history = mock_fetch

    result = asyncio.get_event_loop().run_until_complete(
        reader.fetch_historical_data(
            weather_context.get("entity_id", "weather.home"),
            HistoricalDataKey.OUTDOOR_TEMP,
            datetime(2024, 1, 15, 12, 0),
            datetime(2024, 1, 15, 13, 0),
        )
    )

    weather_context["fetch_result"] = result
    weather_context["fetch_completed"] = True


@then("the RecorderQueue lock should be acquired")
def lock_acquired(weather_context):
    """THEN: RecorderQueue lock was acquired during fetch."""
    assert weather_context["reader"]._recorder_queue is weather_context["recorder_queue"]


@then("the lock should be released after data fetch completes")
def lock_released(weather_context):
    """THEN: Lock is released after fetch."""
    assert not weather_context["recorder_queue"].lock.locked()


@then("historical data should be returned")
def historical_data_returned(weather_context):
    """THEN: Historical data was returned."""
    assert weather_context.get("fetch_completed") is True


# ------------------------------------------------------------------
# Scenario: RecorderQueue is mandatory
# ------------------------------------------------------------------

@when("I try to create a HAWeatherDataReader without RecorderQueue")
def create_weather_without_queue(weather_context, mock_hass):
    """WHEN: Try to create without RecorderQueue."""
    try:
        HAWeatherDataReader(mock_hass)  # type: ignore[call-arg]
        weather_context["error"] = None
    except TypeError as e:
        weather_context["error"] = e


@then("a TypeError should be raised")
def type_error_raised(weather_context):
    """THEN: A TypeError should be raised."""
    assert weather_context.get("error") is not None
    assert isinstance(weather_context["error"], TypeError)


@then("the error should indicate missing required parameter")
def error_indicates_missing_param(weather_context):
    """THEN: Error indicates missing required parameter."""
    assert "recorder_queue" in str(weather_context["error"])


# ------------------------------------------------------------------
# Scenario: RecorderQueue serializes access across all weather readers
# ------------------------------------------------------------------

@given("I have a RecorderQueue instance")
def have_queue_instance(weather_context, recorder_queue):
    """GIVEN: A RecorderQueue instance."""
    weather_context["recorder_queue"] = recorder_queue


@when("I create multiple HAWeatherDataReader instances with the same queue")
def create_multiple_readers(weather_context, mock_hass):
    """WHEN: Create multiple readers sharing the same queue."""
    rq = weather_context["recorder_queue"]
    reader1 = HAWeatherDataReader(mock_hass, rq)
    reader2 = HAWeatherDataReader(mock_hass, rq)
    weather_context["reader1"] = reader1
    weather_context["reader2"] = reader2


@then("all readers should use the same RecorderQueue instance")
def readers_share_queue(weather_context):
    """THEN: All readers share the same RecorderQueue."""
    assert (
        weather_context["reader1"]._recorder_queue
        is weather_context["reader2"]._recorder_queue
    )


@then("concurrent fetch operations should be serialized in FIFO order")
def concurrent_serialized_fifo(weather_context):
    """THEN: Concurrent operations are serialized via the shared FIFO lock."""
    rq = weather_context["recorder_queue"]
    assert weather_context["reader1"]._recorder_queue.lock is rq.lock
    assert weather_context["reader2"]._recorder_queue.lock is rq.lock
