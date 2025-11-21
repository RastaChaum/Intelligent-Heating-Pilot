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
    async def test_get_scheduled_target_time_with_matching_schedule_outofrange(
        self, reader_with_scheduler, mock_hass
    ):
        """Test finding scheduled time from scheduler history."""
        from homeassistant.util import dt as dt_util
        
        cycle_start = dt_util.as_local(datetime(2024, 1, 15, 7, 0, 0))
        cycle_end = dt_util.as_local(datetime(2024, 1, 15, 8, 0, 0))
        expected_scheduled_time = dt_util.as_local(datetime(2024, 1, 15, 11, 1, 0))
        
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
        
        assert result is None
        # Check that times are close (allowing for timezone differences)


    @pytest.mark.asyncio
    async def test_get_scheduled_target_time_with_matching_schedule_after(
        self, reader_with_scheduler, mock_hass
    ):
        """Test finding scheduled time from scheduler history."""
        from homeassistant.util import dt as dt_util
        
        cycle_start = dt_util.as_local(datetime(2024, 1, 15, 7, 0, 0))
        cycle_end = dt_util.as_local(datetime(2024, 1, 15, 8, 0, 0))
        expected_scheduled_time = dt_util.as_local(datetime(2024, 1, 15, 9, 0, 0))
        
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
        assert time_diff < 10800  # Within 3 hours

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


class TestSimplifiedCycleDetection:
    """Tests for the simplified heating cycle detection logic."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.is_running = True
        return hass

    @pytest.fixture
    def reader(self, mock_hass):
        """Create reader without scheduler (tests simplified cycle detection)."""
        return HAHistoricalDataReader(mock_hass)

    def _create_climate_state(
        self, timestamp: datetime, hvac_mode: str, current_temp: float, target_temp: float
    ):
        """Helper to create a mock climate state."""
        state = Mock()
        state.state = hvac_mode
        state.last_changed = timestamp
        state.attributes = {
            "current_temperature": current_temp,
            "temperature": target_temp,
        }
        return state

    @pytest.mark.asyncio
    async def test_cycle_detection_basic_heating_cycle(self, reader):
        """Test detection of a basic heating cycle: start when gap>=0.3°C, end when gap<0.3°C."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence:
        # 1. Heating starts with 19.5°C, target 20°C (gap=0.5°C) - CYCLE START
        # 2. Temperature rises to 19.8°C, target still 20°C (gap=0.2°C) - CYCLE END
        states = [
            self._create_climate_state(start_time, "heat", 19.5, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=30), "heat", 19.8, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=1),
        )
        
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.initial_temp == 19.5
        assert cycle.target_temp == 20.0
        assert cycle.final_temp == 19.8
        assert abs(cycle.actual_duration_minutes - 30.0) < 0.1

    @pytest.mark.asyncio
    async def test_cycle_detection_hvac_mode_change_ends_cycle(self, reader):
        """Test that changing HVAC mode to non-heat ends the cycle."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence:
        # 1. Heating starts with 19.0°C, target 20°C (gap=1.0°C) - CYCLE START
        # 2. HVAC switches to "off" before reaching target - CYCLE END
        states = [
            self._create_climate_state(start_time, "heat", 19.0, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=20), "off", 19.3, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=1),
        )
        
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.initial_temp == 19.0
        assert cycle.final_temp == 19.3
        assert abs(cycle.actual_duration_minutes - 20.0) < 0.1

    @pytest.mark.asyncio
    async def test_cycle_detection_threshold_0_3_degrees(self, reader):
        """Test that 0.3°C threshold is correctly applied for cycle start/end."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence testing the boundary:
        # 1. gap=0.29°C (19.71, target 20.0) - NO CYCLE (below threshold)
        # 2. gap=0.3°C (19.7, target 20.0) - CYCLE START (at threshold)
        # 3. gap=0.29°C (19.71, target 20.0) - CYCLE END (below threshold)
        states = [
            self._create_climate_state(start_time, "heat", 19.71, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=10), "heat", 19.7, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=40), "heat", 19.71, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=1),
        )
        
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.initial_temp == 19.7
        assert abs(cycle.actual_duration_minutes - 30.0) < 0.1

    @pytest.mark.asyncio
    async def test_cycle_detection_multiple_cycles(self, reader):
        """Test detection of multiple sequential heating cycles."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence with TWO cycles:
        # Cycle 1: Start at 19.0°C, end when reaches 19.8°C
        # Cycle 2: Start at 18.5°C, end when HVAC turns off
        states = [
            # Cycle 1
            self._create_climate_state(start_time, "heat", 19.0, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=30), "heat", 19.8, 20.0),
            # Between cycles
            self._create_climate_state(start_time + timedelta(minutes=60), "off", 19.5, 20.0),
            # Cycle 2
            self._create_climate_state(start_time + timedelta(minutes=120), "heat", 18.5, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=150), "off", 19.0, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=3),
        )
        
        assert len(cycles) == 2
        
        # Validate cycle 1
        assert cycles[0].initial_temp == 19.0
        assert cycles[0].final_temp == 19.8
        assert abs(cycles[0].actual_duration_minutes - 30.0) < 0.1
        
        # Validate cycle 2
        assert cycles[1].initial_temp == 18.5
        assert cycles[1].final_temp == 19.0
        assert abs(cycles[1].actual_duration_minutes - 30.0) < 0.1

    @pytest.mark.asyncio
    async def test_cycle_detection_no_cycle_when_temp_gap_too_small(self, reader):
        """Test that no cycle is detected if temperature gap never reaches 0.3°C."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence where gap is always < 0.3°C
        states = [
            self._create_climate_state(start_time, "heat", 19.75, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=30), "heat", 19.8, 20.0),
            self._create_climate_state(start_time + timedelta(minutes=60), "off", 19.85, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=2),
        )
        
        assert len(cycles) == 0

    @pytest.mark.asyncio
    async def test_cycle_detection_skips_states_with_missing_data(self, reader):
        """Test that states with missing temperature data are skipped."""
        start_time = datetime(2024, 1, 15, 7, 0, 0)
        
        # Create state sequence with some None values
        state_with_none = Mock()
        state_with_none.state = "heat"
        state_with_none.last_changed = start_time + timedelta(minutes=15)
        state_with_none.attributes = {
            "current_temperature": None,  # Missing data
            "temperature": 20.0,
        }
        
        states = [
            self._create_climate_state(start_time, "heat", 19.0, 20.0),
            state_with_none,
            self._create_climate_state(start_time + timedelta(minutes=30), "heat", 19.8, 20.0),
        ]
        
        reader._get_entity_states = AsyncMock(return_value=states)
        reader._get_slope_at_time = AsyncMock(return_value=1.5)
        reader._get_scheduled_target_time = AsyncMock(return_value=None)
        
        cycles = await reader.get_heating_cycles(
            "climate.test_room",
            start_time - timedelta(hours=1),
            start_time + timedelta(hours=1),
        )
        
        # Should still detect the cycle, skipping the invalid state
        assert len(cycles) == 1
        assert cycles[0].initial_temp == 19.0
