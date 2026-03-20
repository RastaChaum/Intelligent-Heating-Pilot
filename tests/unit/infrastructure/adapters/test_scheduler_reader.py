"""Tests for HASchedulerReader adapter."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
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
async def test_get_next_timeslot_entity_not_found(
    reader: HASchedulerReader, mock_hass: Mock, scheduler_entities: list[str]
) -> None:
    """Test getting timeslot when entity doesn't exist."""
    # Mock: entity not found
    mock_hass.states.get.return_value = None

    # Execute
    result = await reader.get_next_timeslot()

    # Assert
    assert result is None
    mock_hass.states.get.assert_called_with("switch.heating_schedule")


@pytest.mark.asyncio
async def test_get_next_timeslot_standard_format(
    reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test getting timeslot with standard scheduler format."""
    # Mock: scheduler state with standard format
    mock_state = Mock()
    mock_state.state = "on"  # Scheduler is enabled
    mock_state.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
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
async def test_get_next_timeslot_scheduler_disabled(
    reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that disabled schedulers are skipped."""
    # Mock: scheduler state with "off" state
    mock_state = Mock()
    mock_state.state = "off"  # Scheduler is disabled
    mock_state.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
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
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1", "switch.schedule_2"])

    # Mock: two scheduler states
    mock_state_1 = Mock()
    mock_state_1.state = "on"  # Enabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
    }

    mock_state_2 = Mock()
    mock_state_2.state = "on"  # Enabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",  # Earlier time
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}],
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
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1", "switch.schedule_2"])

    # Mock: one enabled, one disabled
    mock_state_1 = Mock()
    mock_state_1.state = "off"  # Disabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T06:00:00+01:00",  # Earlier time but disabled
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
    }

    mock_state_2 = Mock()
    mock_state_2.state = "on"  # Enabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",  # Later time but enabled
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}],
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
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1", "switch.schedule_2"])

    # Mock: both disabled
    mock_state_1 = Mock()
    mock_state_1.state = "off"  # Disabled
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
    }

    mock_state_2 = Mock()
    mock_state_2.state = "off"  # Disabled
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22.0}}],
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
    action = {"service": "climate.set_temperature", "data": {"temperature": 21.5}}

    result = reader._extract_temp_from_action(action)

    assert result == 21.5


def test_extract_temp_from_action_invalid(reader: HASchedulerReader) -> None:
    """Test extracting temperature from invalid action."""
    # Test with no temperature
    action = {"service": "climate.set_temperature", "data": {}}
    result = reader._extract_temp_from_action(action)
    assert result is None

    # Test with invalid service
    action = {"service": "light.turn_on", "data": {"brightness": 255}}
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
        },
    }

    reader = HASchedulerReader(
        mock_hass, ["switch.schedule"], vtherm_entity_id="climate.test_vtherm"
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
        },
    }

    reader = HASchedulerReader(
        mock_hass, ["switch.schedule"], vtherm_entity_id="climate.test_vtherm"
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
async def test_is_scheduler_enabled_entity_not_found(
    reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled returns False when entity not found."""
    mock_hass.states.get.return_value = None

    result = await reader.is_scheduler_enabled("switch.heating_schedule")

    assert result is False
    mock_hass.states.get.assert_called_once_with("switch.heating_schedule")


# ── Native HA Schedule (schedule.*) tests ─────────────────────────────────────


@pytest.fixture
def native_schedule_reader(mock_hass: Mock) -> HASchedulerReader:
    """Create a HASchedulerReader configured with a native HA schedule entity."""
    return HASchedulerReader(mock_hass, ["schedule.planning_chauffage"])


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_off_state(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that native schedule in OFF state provides next ON time for preheating.

    When a native HA schedule is OFF, next_event points to the next ON time,
    which is what we want for preheating anticipation.
    """
    mock_state = Mock()
    mock_state.entity_id = "schedule.planning_chauffage"
    mock_state.state = "off"  # Not in active timeslot
    mock_state.attributes = {
        "next_event": "2024-01-15T07:00:00+01:00",  # Next ON time
        "friendly_name": "Planning Chauffage",
    }
    mock_hass.states.get.return_value = mock_state
    mock_hass.is_running = True

    result = await native_schedule_reader.get_next_timeslot()

    assert result is not None
    assert isinstance(result, ScheduledTimeslot)
    assert result.target_time is not None
    assert result.target_temp == 20.0  # Default temperature (no VTherm configured)
    assert result.timeslot_id.startswith("schedule.planning_chauffage_")


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_on_state_skipped(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that native schedule in ON state is skipped (next_event = next OFF time).

    When a native HA schedule is ON, next_event points to the next OFF time,
    not an ON time. IHP should skip this to avoid anticipating the end of heating.
    """
    mock_state = Mock()
    mock_state.entity_id = "schedule.planning_chauffage"
    mock_state.state = "on"  # Currently in active timeslot
    mock_state.attributes = {
        "next_event": "2024-01-15T09:00:00+01:00",  # Next OFF time - should be ignored
        "friendly_name": "Planning Chauffage",
    }
    mock_hass.states.get.return_value = mock_state
    mock_hass.is_running = True

    result = await native_schedule_reader.get_next_timeslot()

    # Should be None because schedule is ON (next_event = next OFF time)
    assert result is None


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_no_next_event(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that native schedule with missing next_event attribute returns None."""
    mock_state = Mock()
    mock_state.entity_id = "schedule.planning_chauffage"
    mock_state.state = "off"
    mock_state.attributes = {
        "friendly_name": "Planning Chauffage",
        # No next_event attribute
    }
    mock_hass.states.get.return_value = mock_state
    mock_hass.is_running = True

    result = await native_schedule_reader.get_next_timeslot()

    assert result is None


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_with_climate_reader_temperature(
    mock_hass: Mock,
) -> None:
    """Test that native schedule resolves temperature via the injected climate reader."""
    mock_climate_reader = Mock()
    mock_climate_reader.get_current_target_temperature.return_value = 21.5

    reader = HASchedulerReader(
        mock_hass,
        ["schedule.planning_chauffage"],
        climate_reader=mock_climate_reader,
    )

    schedule_state = Mock()
    schedule_state.entity_id = "schedule.planning_chauffage"
    schedule_state.state = "off"
    schedule_state.attributes = {
        "next_event": "2024-01-15T07:00:00+01:00",
        "friendly_name": "Planning Chauffage",
    }

    mock_hass.states.get.return_value = schedule_state
    mock_hass.is_running = True

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.target_temp == 21.5  # Temperature from climate reader
    mock_climate_reader.get_current_target_temperature.assert_called_once()


@pytest.mark.asyncio
async def test_is_scheduler_enabled_native_schedule_always_true(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled always returns True for native schedule entities.

    Native HA schedules are always considered enabled, regardless of their state.
    The "off" state means the schedule is not in an active timeslot, not disabled.
    """
    # Even when state is "off", native schedule should be considered enabled
    mock_state = Mock()
    mock_state.state = "off"
    mock_hass.states.get.return_value = mock_state

    result = await native_schedule_reader.is_scheduler_enabled("schedule.planning_chauffage")

    assert result is True
    # Should NOT call hass.states.get since we return early for schedule.* entities
    mock_hass.states.get.assert_not_called()


@pytest.mark.asyncio
async def test_is_scheduler_enabled_native_schedule_on_also_true(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled returns True for ON native schedule entities."""
    mock_state = Mock()
    mock_state.state = "on"
    mock_hass.states.get.return_value = mock_state

    result = await native_schedule_reader.is_scheduler_enabled("schedule.planning_chauffage")

    assert result is True
    mock_hass.states.get.assert_not_called()


def test_parse_datetime_value_datetime_object(reader: HASchedulerReader) -> None:
    """Test that _parse_datetime_value handles datetime objects directly."""
    dt = datetime(2024, 1, 15, 7, 0, 0, tzinfo=timezone.utc)

    result = reader._parse_datetime_value(dt)

    assert result == dt
    assert result.tzinfo is not None


def test_parse_datetime_value_iso_string(reader: HASchedulerReader) -> None:
    """Test that _parse_datetime_value handles ISO format strings."""
    iso_str = "2024-01-15T07:00:00+01:00"

    result = reader._parse_datetime_value(iso_str)

    assert result is not None
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_parse_datetime_value_none(reader: HASchedulerReader) -> None:
    """Test that _parse_datetime_value returns None for None input."""
    result = reader._parse_datetime_value(None)

    assert result is None


def test_parse_datetime_value_naive_datetime_gets_timezone(reader: HASchedulerReader) -> None:
    """Test that _parse_datetime_value adds timezone to naive datetime objects."""
    naive_dt = datetime(2024, 1, 15, 7, 0, 0)  # No tzinfo

    result = reader._parse_datetime_value(naive_dt)

    assert result is not None
    assert result.tzinfo is not None


def test_get_native_schedule_temperature_no_climate_reader(reader: HASchedulerReader) -> None:
    """Test that _get_native_schedule_temperature returns the default when no climate reader configured."""
    result = reader._get_native_schedule_temperature()

    assert result == 20.0


def test_get_native_schedule_temperature_climate_reader_returns_none(mock_hass: Mock) -> None:
    """Test that _get_native_schedule_temperature returns 20.0°C when climate reader returns None."""
    mock_climate_reader = Mock()
    mock_climate_reader.get_current_target_temperature.return_value = None
    reader = HASchedulerReader(
        mock_hass, ["schedule.test"], climate_reader=mock_climate_reader
    )

    result = reader._get_native_schedule_temperature()

    assert result == 20.0
    mock_climate_reader.get_current_target_temperature.assert_called_once()


def test_get_native_schedule_temperature_from_climate_reader(mock_hass: Mock) -> None:
    """Test that _get_native_schedule_temperature reads temperature from the climate reader."""
    mock_climate_reader = Mock()
    mock_climate_reader.get_current_target_temperature.return_value = 22.0
    reader = HASchedulerReader(
        mock_hass, ["schedule.test"], climate_reader=mock_climate_reader
    )

    result = reader._get_native_schedule_temperature()

    assert result == 22.0
    mock_climate_reader.get_current_target_temperature.assert_called_once()


@pytest.mark.asyncio
async def test_get_next_timeslot_mixed_native_and_hacs(mock_hass: Mock) -> None:
    """Test that native schedule and HACS scheduler work together correctly.

    IHP should correctly handle a mix of native HA schedule and HACS switch
    entities, picking the earliest valid timeslot.
    """
    reader = HASchedulerReader(
        mock_hass,
        ["schedule.native_schedule", "switch.hacs_schedule"],
    )

    # Native schedule: OFF, next_event at 07:00 (next ON time)
    native_state = Mock()
    native_state.entity_id = "schedule.native_schedule"
    native_state.state = "off"
    native_state.attributes = {
        "next_event": "2024-01-15T07:00:00+01:00",
        "friendly_name": "Native Schedule",
    }

    # HACS schedule: ON, next_trigger at 08:00
    hacs_state = Mock()
    hacs_state.entity_id = "switch.hacs_schedule"
    hacs_state.state = "on"
    hacs_state.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
        "friendly_name": "HACS Schedule",
    }

    def mock_get_state(entity_id: str) -> Mock | None:
        if entity_id == "schedule.native_schedule":
            return native_state
        if entity_id == "switch.hacs_schedule":
            return hacs_state
        return None

    mock_hass.states.get.side_effect = mock_get_state
    mock_hass.is_running = True

    result = await reader.get_next_timeslot()

    # Should pick the earlier native schedule timeslot
    assert result is not None
    assert result.scheduler_entity == "schedule.native_schedule"
