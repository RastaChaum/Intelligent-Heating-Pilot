"""Unit tests for Home Assistant weather data adapter (TDD)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataSet,
    HistoricalDataKey,
    HistoricalMeasurement,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.weather_data_adapter import (
    WeatherDataAdapter,
)
from tests.unit.domain.fixtures import (
    get_test_datetime,
    get_future_datetime,
    TEST_ENTITY_ID,
    MOCK_WEATHER_HISTORY_RESPONSE,
)


class TestWeatherDataAdapter:
    """Tests for WeatherDataAdapter."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def adapter(self, mock_hass):
        """Create a WeatherDataAdapter instance for testing."""
        return WeatherDataAdapter(mock_hass)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_returns_historical_dataset(self, adapter):
        """Test that fetch_historical_data returns a HistoricalDataSet."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        assert isinstance(result, HistoricalDataSet)
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_outdoor_temperature(self, adapter):
        """Test that outdoor temperature is correctly extracted from weather data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data("weather.home", HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        assert HistoricalDataKey.OUTDOOR_TEMP in result.data
        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        assert len(outdoor_temps) == 3

        # Verify first measurement
        assert isinstance(outdoor_temps[0], HistoricalMeasurement)
        assert outdoor_temps[0].value == 5.0
        assert outdoor_temps[0].timestamp == datetime(2024, 1, 15, 12, 0, 0)
        assert outdoor_temps[0].entity_id == "weather.home"

        # Verify second measurement
        assert outdoor_temps[1].value == 6.0
        assert outdoor_temps[1].entity_id == "weather.home"
        
        # Verify third measurement
        assert outdoor_temps[2].value == 7.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_outdoor_humidity(self, adapter):
        """Test that outdoor humidity is correctly extracted from weather data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_HUMIDITY, start_time, end_time)

        assert HistoricalDataKey.OUTDOOR_HUMIDITY in result.data
        outdoor_humidity = result.data[HistoricalDataKey.OUTDOOR_HUMIDITY]
        assert len(outdoor_humidity) == 3

        # Verify humidity values
        assert outdoor_humidity[0].value == 75.0
        assert outdoor_humidity[1].value == 70.0
        assert outdoor_humidity[2].value == 65.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_cloud_coverage(self, adapter):
        """Test that cloud coverage is correctly extracted from weather data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.CLOUD_COVERAGE, start_time, end_time)

        assert HistoricalDataKey.CLOUD_COVERAGE in result.data
        cloud_coverage = result.data[HistoricalDataKey.CLOUD_COVERAGE]
        assert len(cloud_coverage) == 3

        # Verify cloud coverage values
        assert cloud_coverage[0].value == 80.0
        assert cloud_coverage[1].value == 50.0
        assert cloud_coverage[2].value == 20.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_preserves_weather_state(self, adapter):
        """Test that weather state is preserved in attributes."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        
        # Verify weather state is preserved in attributes
        assert outdoor_temps[0].attributes["weather_state"] == "rainy"
        assert outdoor_temps[1].attributes["weather_state"] == "cloudy"
        assert outdoor_temps[2].attributes["weather_state"] == "sunny"

    @pytest.mark.asyncio
    async def test_fetch_historical_data_preserves_attributes(self, adapter):
        """Test that additional attributes are preserved in measurements."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        
        # Verify attributes are preserved
        first_measurement = outdoor_temps[0]
        assert "weather_state" in first_measurement.attributes
        assert "humidity" in first_measurement.attributes
        assert "cloud_coverage" in first_measurement.attributes

    @pytest.mark.asyncio
    async def test_fetch_historical_data_with_invalid_entity_id_raises_error(self, adapter):
        """Test that invalid entity ID raises ValueError."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(side_effect=ValueError("Entity not found"))

        with pytest.raises(ValueError, match="Cannot fetch history for entity"):
            await adapter.fetch_historical_data("invalid.entity", HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_with_empty_history(self, adapter):
        """Test handling of empty historical data."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=[])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        assert isinstance(result, HistoricalDataSet)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_converts_timestamps_to_datetime(self, adapter):
        """Test that string timestamps are converted to datetime objects."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_WEATHER_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time)

        outdoor_temps = result.data[HistoricalDataKey.OUTDOOR_TEMP]
        
        # Verify all timestamps are datetime objects, not strings
        for measurement in outdoor_temps:
            assert isinstance(measurement.timestamp, datetime)
