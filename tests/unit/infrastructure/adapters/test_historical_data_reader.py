"""Tests for HAHistoricalDataReader adapter."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.historical_data_reader import (
    HAHistoricalDataReader,
)


class TestHAHistoricalDataReader:
    """Tests for HAHistoricalDataReader scheduler integration."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.is_running = True
        return hass

    @pytest.fixture
    def reader_with_scheduler(self, mock_hass):
        """Create reader with scheduler entities configured."""
        return HAHistoricalDataReader(
            mock_hass,
            scheduler_entity_ids=["schedule.heating_schedule"],
        )

    @pytest.fixture
    def reader_without_scheduler(self, mock_hass):
        """Create reader without scheduler entities."""
        return HAHistoricalDataReader(mock_hass)

    def test_init_with_scheduler_entities(self, mock_hass):
        """Test initialization with scheduler entity IDs."""
        reader = HAHistoricalDataReader(
            mock_hass,
            scheduler_entity_ids=["schedule.heating_schedule"],
        )
        assert reader._scheduler_entity_ids == ["schedule.heating_schedule"]

    def test_init_without_scheduler_entities(self, mock_hass):
        """Test initialization without scheduler entity IDs."""
        reader = HAHistoricalDataReader(mock_hass)
        assert reader._scheduler_entity_ids == []

    def test_parse_next_trigger_valid_iso(self, reader_with_scheduler):
        """Test parsing a valid ISO format next_trigger."""
        result = reader_with_scheduler._parse_next_trigger("2024-01-15T08:00:00+00:00")
        assert result is not None
        assert result.hour == 8
        assert result.minute == 0

    def test_parse_next_trigger_none(self, reader_with_scheduler):
        """Test parsing None next_trigger."""
        result = reader_with_scheduler._parse_next_trigger(None)
        assert result is None

    def test_parse_next_trigger_invalid(self, reader_with_scheduler):
        """Test parsing invalid next_trigger."""
        result = reader_with_scheduler._parse_next_trigger("invalid-date")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_scheduled_target_time_no_scheduler_entities(
        self, reader_without_scheduler
    ):
        """Test that None is returned when no scheduler entities configured."""
        cycle_start = datetime.now()
        cycle_end = cycle_start + timedelta(hours=1)

        result = await reader_without_scheduler._get_scheduled_target_time(
            cycle_start, cycle_end
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_scheduled_target_time_with_matching_schedule(
        self, reader_with_scheduler, mock_hass
    ):
        """Test finding scheduled time from scheduler history."""
        from homeassistant.util import dt as dt_util
        
        cycle_start = dt_util.as_local(datetime(2024, 1, 15, 7, 0, 0))
        cycle_end = dt_util.as_local(datetime(2024, 1, 15, 8, 0, 0))
        expected_scheduled_time = dt_util.as_local(datetime(2024, 1, 15, 8, 0, 0))
        
        # Mock scheduler state with next_trigger
        mock_state = Mock()
        mock_state.attributes = {
            "next_trigger": expected_scheduled_time.isoformat(),
        }
        
        # Mock _get_entity_states to return our mock state
        reader_with_scheduler._get_entity_states = AsyncMock(
            return_value=[mock_state]
        )
        
        result = await reader_with_scheduler._get_scheduled_target_time(
            cycle_start, cycle_end
        )
        
        assert result is not None
        # Check that times are close (allowing for timezone differences)
        time_diff = abs((result - expected_scheduled_time).total_seconds())
        assert time_diff < 60  # Within 1 minute

    @pytest.mark.asyncio
    async def test_get_scheduled_target_time_no_matching_schedule(
        self, reader_with_scheduler
    ):
        """Test that None is returned when no matching schedule found."""
        cycle_start = datetime(2024, 1, 15, 7, 0, 0)
        cycle_end = datetime(2024, 1, 15, 8, 0, 0)
        
        # Mock scheduler state with next_trigger far in the future (no match)
        mock_state = Mock()
        mock_state.attributes = {
            "next_trigger": "2024-01-15T20:00:00+00:00",  # 12 hours later
        }
        
        reader_with_scheduler._get_entity_states = AsyncMock(
            return_value=[mock_state]
        )
        
        result = await reader_with_scheduler._get_scheduled_target_time(
            cycle_start, cycle_end
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_scheduled_target_time_no_history(
        self, reader_with_scheduler
    ):
        """Test that None is returned when no scheduler history found."""
        cycle_start = datetime(2024, 1, 15, 7, 0, 0)
        cycle_end = datetime(2024, 1, 15, 8, 0, 0)
        
        # Mock empty history
        reader_with_scheduler._get_entity_states = AsyncMock(return_value=[])
        
        result = await reader_with_scheduler._get_scheduled_target_time(
            cycle_start, cycle_end
        )
        
        assert result is None
