"""Unit tests verifying data adapters use RecorderAccessQueue when provided."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
    ClimateDataAdapter,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.sensor_data_adapter import (
    SensorDataAdapter,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.weather_data_adapter import (
    WeatherDataAdapter,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)


class TestAdaptersWithRecorderQueue:
    """Tests verifying that adapters serialize recorder access via the queue."""

    @pytest.fixture
    def recorder_queue(self) -> RecorderAccessQueue:
        """Create a RecorderAccessQueue."""
        return RecorderAccessQueue()

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_sensor_adapter_stores_queue(self, mock_hass, recorder_queue):
        """Sensor adapter stores the recorder queue reference."""
        adapter = SensorDataAdapter(mock_hass, recorder_queue=recorder_queue)
        assert adapter._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_climate_adapter_stores_queue(self, mock_hass, recorder_queue):
        """Climate adapter stores the recorder queue reference."""
        adapter = ClimateDataAdapter(mock_hass, recorder_queue=recorder_queue)
        assert adapter._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_weather_adapter_stores_queue(self, mock_hass, recorder_queue):
        """Weather adapter stores the recorder queue reference."""
        adapter = WeatherDataAdapter(mock_hass, recorder_queue=recorder_queue)
        assert adapter._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_adapters_without_queue_still_work(self, mock_hass):
        """Adapters work normally when no recorder queue is provided."""
        sensor_adapter = SensorDataAdapter(mock_hass)
        climate_adapter = ClimateDataAdapter(mock_hass)
        weather_adapter = WeatherDataAdapter(mock_hass)

        assert sensor_adapter._recorder_queue is None
        assert climate_adapter._recorder_queue is None
        assert weather_adapter._recorder_queue is None

    @pytest.mark.asyncio
    async def test_all_adapters_share_same_queue(self, mock_hass, recorder_queue):
        """All adapter types can share the same queue instance."""
        sensor = SensorDataAdapter(mock_hass, recorder_queue=recorder_queue)
        climate = ClimateDataAdapter(mock_hass, recorder_queue=recorder_queue)
        weather = WeatherDataAdapter(mock_hass, recorder_queue=recorder_queue)

        assert sensor._recorder_queue is climate._recorder_queue
        assert climate._recorder_queue is weather._recorder_queue
        assert sensor._recorder_queue.lock is recorder_queue.lock
