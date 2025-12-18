"""Unit tests for Home Assistant sensor data adapter (TDD)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataSet,
    HistoricalDataKey,
    HistoricalMeasurement,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.sensor_data_adapter import (
    SensorDataAdapter,
)
from tests.unit.domain.fixtures import (
    get_test_datetime,
    get_future_datetime,
    TEST_ENTITY_ID,
    MOCK_SENSOR_HISTORY_RESPONSE,
)


class TestSensorDataAdapter:
    """Tests for SensorDataAdapter."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def adapter(self, mock_hass):
        """Create a SensorDataAdapter instance for testing."""
        return SensorDataAdapter(mock_hass)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_returns_historical_dataset(self, adapter):
        """Test that fetch_historical_data returns a HistoricalDataSet."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_SENSOR_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            TEST_ENTITY_ID,
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        assert isinstance(result, HistoricalDataSet)
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_outdoor_temperature(self, adapter):
        """Test that outdoor temperature is correctly extracted from sensor data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_SENSOR_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "some_id",
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        assert HistoricalDataKey.OUTDOOR_TEMP in result.data
        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        assert len(outdoor_temps) == 3

        # Verify first measurement
        assert isinstance(outdoor_temps[0], HistoricalMeasurement)
        assert outdoor_temps[0].value == 5.0
        assert outdoor_temps[0].timestamp == datetime(2024, 1, 15, 12, 0, 0)
        assert outdoor_temps[0].entity_id == "sensor.outdoor_temp"  # Entity ID from mock data

        # Verify second measurement
        assert outdoor_temps[1].value == 6.0
        assert outdoor_temps[1].entity_id == "sensor.outdoor_temp"  # Entity ID from mock data
        
        # Verify third measurement
        assert outdoor_temps[2].value == 7.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_uses_provided_data_key(self, adapter):
        """Test that the provided data_key is used to categorize measurements."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        # Mock data with device_class=humidity
        mock_humidity_data = [
            {
                "entity_id": "sensor.living_room_humidity",
                "state": "45",
                "attributes": {"device_class": "humidity", "unit_of_measurement": "%"},
                "last_changed": "2024-01-15T12:00:00+00:00",
            }
        ]
        adapter._fetch_history = AsyncMock(return_value=mock_humidity_data)

        # Explicitly pass INDOOR_HUMIDITY as the data key
        result = await adapter.fetch_historical_data(
            "sensor.living_room_humidity",
            HistoricalDataKey.INDOOR_HUMIDITY,
            start_time,
            end_time
        )

        # Should use the provided INDOOR_HUMIDITY key
        assert HistoricalDataKey.INDOOR_HUMIDITY in result.data
        assert len(result.data[HistoricalDataKey.INDOOR_HUMIDITY]) == 1

    @pytest.mark.asyncio
    async def test_fetch_historical_data_preserves_attributes(self, adapter):
        """Test that additional attributes are preserved in measurements."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_SENSOR_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "sensor.outdoor_temp",
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        
        # Verify attributes are preserved
        first_measurement = outdoor_temps[0]
        assert "device_class" in first_measurement.attributes
        assert first_measurement.attributes["device_class"] == "temperature"

    @pytest.mark.asyncio
    async def test_fetch_historical_data_with_invalid_entity_id_raises_error(self, adapter):
        """Test that invalid entity ID raises ValueError."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(side_effect=ValueError("Entity not found"))

        with pytest.raises(ValueError, match="Cannot fetch history for entity"):
            await adapter.fetch_historical_data(
                "invalid.entity",
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time
            )

    @pytest.mark.asyncio
    async def test_fetch_historical_data_with_empty_history(self, adapter):
        """Test handling of empty historical data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=[])

        result = await adapter.fetch_historical_data(
            TEST_ENTITY_ID,
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        assert isinstance(result, HistoricalDataSet)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_converts_timestamps_to_datetime(self, adapter):
        """Test that string timestamps are converted to datetime objects."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_SENSOR_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "sensor.outdoor_temp",
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        
        # Verify all timestamps are datetime objects, not strings
        for measurement in outdoor_temps:
            assert isinstance(measurement.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_handles_non_numeric_states(self, adapter):
        """Test that non-numeric sensor states are skipped gracefully."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        # Mock data with non-numeric states
        mock_invalid_data = [
            {
                "entity_id": "sensor.outdoor_temp",
                "state": "unavailable",
                "attributes": {"device_class": "temperature"},
                "last_changed": "2024-01-15T12:00:00+00:00",
            },
            {
                "entity_id": "sensor.outdoor_temp",
                "state": "5.0",
                "attributes": {"device_class": "temperature"},
                "last_changed": "2024-01-15T12:10:00+00:00",
            }
        ]
        adapter._fetch_history = AsyncMock(return_value=mock_invalid_data)

        result = await adapter.fetch_historical_data(
            "sensor.outdoor_temp",
            HistoricalDataKey.OUTDOOR_TEMP,
            start_time,
            end_time
        )

        # Should skip "unavailable" and only include the valid measurement
        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        assert len(outdoor_temps) == 1
        assert outdoor_temps[0].value == 5.0
