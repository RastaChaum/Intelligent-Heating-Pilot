"""Unit tests verifying data readers use RecorderAccessQueue (MANDATORY)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader import (
    HAClimateDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.sensor_data_reader import (
    HASensorDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.weather_data_reader import (
    HAWeatherDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)


class TestAdaptersWithRecorderQueue:
    """Tests verifying that data readers use RecorderAccessQueue (MANDATORY)."""

    @pytest.fixture
    def recorder_queue(self) -> RecorderAccessQueue:
        """Create a RecorderAccessQueue."""
        return RecorderAccessQueue()

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_sensor_reader_stores_queue(self, mock_hass, recorder_queue):
        """Sensor reader stores the recorder queue reference (MANDATORY)."""
        reader = HASensorDataReader(mock_hass, recorder_queue)
        assert reader._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_climate_reader_stores_queue(self, mock_hass, recorder_queue):
        """Climate reader stores the recorder queue reference (MANDATORY)."""
        reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.test")
        assert reader._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_weather_reader_stores_queue(self, mock_hass, recorder_queue):
        """Weather reader stores the recorder queue reference (MANDATORY)."""
        reader = HAWeatherDataReader(mock_hass, recorder_queue)
        assert reader._recorder_queue is recorder_queue

    @pytest.mark.asyncio
    async def test_all_readers_share_same_queue(self, mock_hass, recorder_queue):
        """All reader types can share the same queue instance."""
        sensor = HASensorDataReader(mock_hass, recorder_queue)
        climate = HAClimateDataReader(mock_hass, recorder_queue, "climate.test")
        weather = HAWeatherDataReader(mock_hass, recorder_queue)

        assert sensor._recorder_queue is climate._recorder_queue
        assert climate._recorder_queue is weather._recorder_queue
        assert sensor._recorder_queue.lock is recorder_queue.lock
