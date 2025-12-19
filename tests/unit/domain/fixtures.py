"""Centralized test fixtures for domain layer tests (DRY principle)."""
from datetime import datetime, timedelta, timezone
import sys
import os

# Add custom_components to path for domain imports
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects.heating import HeatingCycle


def get_test_datetime() -> datetime:
    """Get a fixed datetime for testing.
    
    Returns:
        A datetime object representing 2024-01-15 12:00:00
    """
    return datetime(2024, 1, 15, 12, 0, 0)


def get_future_datetime(hours: int = 2) -> datetime:
    """Get a future datetime for testing.
    
    Args:
        hours: Number of hours in the future
        
    Returns:
        A datetime object in the future
    """
    return get_test_datetime() + timedelta(hours=hours)


def create_test_heating_cycle(
    device_id: str,
    start_time: datetime,
    duration_hours: float = 1.0,
    temp_increase: float = 2.0,
) -> HeatingCycle:
    """Create a test heating cycle with default values.
    
    Args:
        device_id: Device identifier for the cycle
        start_time: Cycle start time
        duration_hours: Duration in hours (default: 1.0)
        temp_increase: Temperature increase in °C (default: 2.0)
        
    Returns:
        HeatingCycle object for testing
    """
    end_time = start_time + timedelta(hours=duration_hours)
    start_temp = 18.0
    end_temp = start_temp + temp_increase
    target_temp = end_temp + 0.5
    
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=target_temp,
        end_temp=end_temp,
        start_temp=start_temp,
        tariff_details=None
    )


# Standard test values
TEST_CURRENT_TEMP = 18.0
TEST_TARGET_TEMP = 21.0
TEST_OUTDOOR_TEMP = 10.0
TEST_HUMIDITY = 50.0
TEST_LEARNED_SLOPE = 2.0
TEST_CLOUD_COVERAGE = 50.0

# Test timeslot ID
TEST_TIMESLOT_ID = "test_timeslot_1"

# Test device IDs
TEST_DEVICE_ID = "climate.test_vtherm"
TEST_ENTITY_ID = "climate.living_room"
TEST_SENSOR_ENTITY_ID = "sensor.indoor_temperature"
TEST_WEATHER_ENTITY_ID = "weather.home"

# Home Assistant historical data responses (mocked)
MOCK_CLIMATE_HISTORY_RESPONSE = [
    [
        {
            "entity_id": "climate.living_room",
            "state": "heat",
            "attributes": {
                "current_temperature": 18.0,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
            "last_changed": "2024-01-15T12:00:00+00:00",
            "last_updated": "2024-01-15T12:00:00+00:00",
        },
        {
            "entity_id": "climate.living_room",
            "state": "heat",
            "attributes": {
                "current_temperature": 19.0,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            },
            "last_changed": "2024-01-15T12:15:00+00:00",
            "last_updated": "2024-01-15T12:15:00+00:00",
        },
        {
            "entity_id": "climate.living_room",
            "state": "off",
            "attributes": {
                "current_temperature": 21.0,
                "target_temperature": 21.0,
                "hvac_action": "idle",
            },
            "last_changed": "2024-01-15T12:30:00+00:00",
            "last_updated": "2024-01-15T12:30:00+00:00",
        },
    ]
]

MOCK_SENSOR_HISTORY_RESPONSE = [
    [
        {
            "entity_id": "sensor.outdoor_temp",
            "state": "5.0",
            "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"},
            "last_changed": "2024-01-15T12:00:00+00:00",
            "last_updated": "2024-01-15T12:00:00+00:00",
        },
        {
            "entity_id": "sensor.outdoor_temp",
            "state": "6.0",
            "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"},
            "last_changed": "2024-01-15T12:15:00+00:00",
            "last_updated": "2024-01-15T12:15:00+00:00",
        },
        {
            "entity_id": "sensor.outdoor_temp",
            "state": "7.0",
            "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"},
            "last_changed": "2024-01-15T12:30:00+00:00",
            "last_updated": "2024-01-15T12:30:00+00:00",
        },
    ]
]

MOCK_WEATHER_HISTORY_RESPONSE = [
    [
        {
            "entity_id": "weather.home",
            "state": "rainy",
            "attributes": {
                "temperature": 5.0,
                "humidity": 75,
                "cloud_coverage": 80,
                "weather_state": "rainy",
            },
            "last_changed": "2024-01-15T12:00:00+00:00",
            "last_updated": "2024-01-15T12:00:00+00:00",
        },
        {
            "entity_id": "weather.home",
            "state": "cloudy",
            "attributes": {
                "temperature": 6.0,
                "humidity": 70,
                "cloud_coverage": 50,
                "weather_state": "cloudy",
            },
            "last_changed": "2024-01-15T12:30:00+00:00",
            "last_updated": "2024-01-15T12:30:00+00:00",
        },
        {
            "entity_id": "weather.home",
            "state": "sunny",
            "attributes": {
                "temperature": 7.0,
                "humidity": 65,
                "cloud_coverage": 20,
                "weather_state": "sunny",
            },
            "last_changed": "2024-01-15T13:00:00+00:00",
            "last_updated": "2024-01-15T13:00:00+00:00",
        },
    ]
]
