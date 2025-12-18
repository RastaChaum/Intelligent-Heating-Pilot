"""Tests for HASchedulerReader adapter."""
from datetime import datetime
from unittest.mock import Mock, MagicMock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def scheduler_entities() -> list[str]:
    """Get list of scheduler entities."""
    return ["switch.heating_schedule"]


@pytest.fixture
def reader(mock_hass: Mock, scheduler_entities: list[str]) -> HASchedulerReader:
    """Create a HASchedulerReader instance."""
    return HASchedulerReader(mock_hass, scheduler_entities)


def test_init(reader: HASchedulerReader, mock_hass: Mock, scheduler_entities: list[str]) -> None:
    """Test adapter initialization."""
    assert reader._scheduler_entity_ids == scheduler_entities
    assert reader._hass == mock_hass


@pytest.mark.asyncio
async def test_get_next_timeslot_no_entities(mock_hass: Mock) -> None:
    """Test getting timeslot when no entities configured."""
    reader = HASchedulerReader(mock_hass, [])
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_get_next_timeslot_entity_not_found(reader: HASchedulerReader, mock_hass: Mock, scheduler_entities: list[str]) -> None:
    """Test getting timeslot when entity doesn't exist."""
    # Mock: entity not found
    mock_hass.states.get.return_value = None
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert
    assert result is None
    mock_hass.states.get.assert_called_once_with("switch.heating_schedule")


@pytest.mark.asyncio
async def test_get_next_timeslot_standard_format(reader: HASchedulerReader, mock_hass: Mock) -> None:
    """Test getting timeslot with standard scheduler format."""
    # Mock: scheduler state with standard format
    mock_state = Mock()
    mock_state.state = "on"  # Scheduler is enabled
    mock_state.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [
            {
                "service": "climate.set_temperature",
                "data": {"temperature": 21.0}
            }
        ]
    }
    mock_hass.states.get.return_value = mock_state
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert
    assert result is not None
    assert isinstance(result, ScheduledTimeslot)
    assert result.target_temp == 21.0
    assert result.target_time is not None
    assert result.timeslot_id.startswith("switch.heating_schedule_")


@pytest.mark.asyncio
async def test_get_next_timeslot_scheduler_disabled(reader: HASchedulerReader, mock_hass: Mock) -> None:
    """Test that disabled schedulers are skipped."""
    # Mock: scheduler state with "off" state
    mock_state = Mock()
    mock_state.state = "off"  # Scheduler is disabled
    mock_state.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [
            {
                "service": "climate.set_temperature",
                "data": {"temperature": 21.0}
            }
        ]
    }
    mock_hass.states.get.return_value = mock_state
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert: should return None since scheduler is disabled
    assert result is None


@pytest.mark.asyncio
async def test_get_next_timeslot_multiple_entities(mock_hass: Mock) -> None:
    """Test getting earliest timeslot from multiple schedulers."""
    # Setup multiple schedulers
    reader = HASchedulerReader(
        mock_hass,
        ["switch.schedule_1", "switch.schedule_2"]
    )
    
    # Mock: two scheduler states
    mock_state_1 = Mock()
    mock_state_1.state = "on"  # Enabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
    }
    
    mock_state_2 = Mock()
    mock_state_2.state = "on"  # Enabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",  # Earlier time
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}]
    }
    
    def mock_get_state(entity_id: str) -> Mock | None:
        if entity_id == "switch.schedule_1":
            return mock_state_1
        elif entity_id == "switch.schedule_2":
            return mock_state_2
        return None
    
    mock_hass.states.get.side_effect = mock_get_state
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert: should return the earlier timeslot
    assert result is not None
    assert result.target_temp == 22.0
    assert result.timeslot_id.startswith("switch.schedule_2_")


@pytest.mark.asyncio
async def test_get_next_timeslot_multiple_entities_one_disabled(mock_hass: Mock) -> None:
    """Test that only enabled schedulers are considered when multiple exist."""
    # Setup multiple schedulers
    reader = HASchedulerReader(
        mock_hass,
        ["switch.schedule_1", "switch.schedule_2"]
    )
    
    # Mock: one enabled, one disabled
    mock_state_1 = Mock()
    mock_state_1.state = "off"  # Disabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T06:00:00+01:00",  # Earlier time but disabled
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
    }
    
    mock_state_2 = Mock()
    mock_state_2.state = "on"  # Enabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",  # Later time but enabled
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}]
    }
    
    def mock_get_state(entity_id: str) -> Mock | None:
        if entity_id == "switch.schedule_1":
            return mock_state_1
        elif entity_id == "switch.schedule_2":
            return mock_state_2
        return None
    
    mock_hass.states.get.side_effect = mock_get_state
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert: should return the enabled scheduler's timeslot
    assert result is not None
    assert result.target_temp == 22.0
    assert result.timeslot_id.startswith("switch.schedule_2_")


@pytest.mark.asyncio
async def test_get_next_timeslot_all_disabled(mock_hass: Mock) -> None:
    """Test that no timeslot is returned when all schedulers are disabled."""
    # Setup multiple schedulers
    reader = HASchedulerReader(
        mock_hass,
        ["switch.schedule_1", "switch.schedule_2"]
    )
    
    # Mock: both disabled
    mock_state_1 = Mock()
    mock_state_1.state = "off"  # Disabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}]
    }
    
    mock_state_2 = Mock()
    mock_state_2.state = "off"  # Disabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}]
    }
    
    def mock_get_state(entity_id: str) -> Mock | None:
        if entity_id == "switch.schedule_1":
            return mock_state_1
        elif entity_id == "switch.schedule_2":
            return mock_state_2
        return None
    
    mock_hass.states.get.side_effect = mock_get_state
    
    # Execute
    result = await reader.get_next_timeslot()
    
    # Assert: should return None since all schedulers are disabled
    assert result is None


def test_extract_temp_from_action_direct(reader: HASchedulerReader) -> None:
    """Test extracting temperature from direct set_temperature action."""
    action = {
        "service": "climate.set_temperature",
        "data": {"temperature": 21.5}
    }
    
    result = reader._extract_temp_from_action(action)
    
    assert result == 21.5


def test_extract_temp_from_action_invalid(reader: HASchedulerReader) -> None:
    """Test extracting temperature from invalid action."""
    # Test with no temperature
    action = {
        "service": "climate.set_temperature",
        "data": {}
    }
    result = reader._extract_temp_from_action(action)
    assert result is None
    
    # Test with invalid service
    action = {
        "service": "light.turn_on",
        "data": {"brightness": 255}
    }
    result = reader._extract_temp_from_action(action)
    assert result is None
    
    # Test with non-dict action
    result = reader._extract_temp_from_action({"invalid": "iji"})
    assert result is None


def test_parse_next_trigger_valid_iso(reader: HASchedulerReader) -> None:
    """Test parsing valid ISO datetime string."""
    trigger_str = "2024-01-15T07:30:00+01:00"
    
    result = reader._parse_next_trigger(trigger_str)
    
    assert result is not None
    assert isinstance(result, datetime)
    assert result.tzinfo is not None  # Should have timezone


def test_parse_next_trigger_none(reader: HASchedulerReader) -> None:
    """Test parsing None trigger."""
    result = reader._parse_next_trigger(None)
    assert result is None


def test_parse_next_trigger_invalid(reader: HASchedulerReader) -> None:
    """Test parsing invalid trigger string."""
    result = reader._parse_next_trigger("not a datetime")
    assert result is None


def test_resolve_preset_temperature_v8_format(mock_hass: Mock) -> None:
    """Test resolving preset temperature from VTherm v8.0.0+ format."""
    # Setup VTherm entity with v8.0.0+ preset_temperatures structure
    vtherm_state = Mock()
    vtherm_state.entity_id = "climate.test_vtherm"
    vtherm_state.attributes = {
        "preset_mode": "none",
        "preset_temperatures": {
            "eco_temp": 18.0,
            "boost_temp": 22.0,
            "comfort_temp": 20.0,
            "frost_temp": 10.0,
        }
    }
    
    reader = HASchedulerReader(
        mock_hass, 
        ["switch.schedule"], 
        vtherm_entity_id="climate.test_vtherm"
    )
    
    # Mock VTherm state
    mock_hass.states.get.return_value = vtherm_state
    
    # Test resolving eco preset
    result = reader._resolve_preset_temperature("eco")
    assert result == 18.0
    
    # Test resolving boost preset
    result = reader._resolve_preset_temperature("boost")
    assert result == 22.0
    
    # Test resolving comfort preset
    result = reader._resolve_preset_temperature("comfort")
    assert result == 20.0


def test_resolve_preset_temperature_ignores_zero_values(mock_hass: Mock) -> None:
    """Test that preset resolution ignores 0 values (uninitialized)."""
    # Setup VTherm with uninitialized presets
    vtherm_state = Mock()
    vtherm_state.entity_id = "climate.test_vtherm"
    vtherm_state.attributes = {
        "preset_mode": "none",
        "preset_temperatures": {
            "eco_temp": 0,  # Uninitialized
            "boost_temp": 0,  # Uninitialized
        }
    }
    
    reader = HASchedulerReader(
        mock_hass, 
        ["switch.schedule"], 
        vtherm_entity_id="climate.test_vtherm"
    )
    
    mock_hass.states.get.return_value = vtherm_state
    
    # Should return None for 0 values
    result = reader._resolve_preset_temperature("eco")
    assert result is None


@pytest.mark.asyncio
async def test_is_scheduler_enabled_on(reader: HASchedulerReader, mock_hass: Mock) -> None:
    """Test that is_scheduler_enabled returns True for enabled schedulers."""
    mock_state = Mock()
    mock_state.state = "on"
    mock_hass.states.get.return_value = mock_state
    
    result = await reader.is_scheduler_enabled("switch.heating_schedule")
    
    assert result is True
    mock_hass.states.get.assert_called_once_with("switch.heating_schedule")


@pytest.mark.asyncio
async def test_is_scheduler_enabled_off(reader: HASchedulerReader, mock_hass: Mock) -> None:
    """Test that is_scheduler_enabled returns False for disabled schedulers."""
    mock_state = Mock()
    mock_state.state = "off"
    mock_hass.states.get.return_value = mock_state
    
    result = await reader.is_scheduler_enabled("switch.heating_schedule")
    
    assert result is False
    mock_hass.states.get.assert_called_once_with("switch.heating_schedule")


@pytest.mark.asyncio
async def test_is_scheduler_enabled_entity_not_found(reader: HASchedulerReader, mock_hass: Mock) -> None:
    """Test that is_scheduler_enabled returns False when entity not found."""
    mock_hass.states.get.return_value = None
    
    result = await reader.is_scheduler_enabled("switch.heating_schedule")
    
    assert result is False
    mock_hass.states.get.assert_called_once_with("switch.heating_schedule")
