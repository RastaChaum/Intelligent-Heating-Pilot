"""Tests for HASchedulerReader adapter."""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
    SlotAction,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader import (
    NativeScheduleSettings,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.preset_temperature_resolver import (
    HAPresetTemperatureResolver,
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
async def test_get_next_timeslot_excludes_given_entities(mock_hass: Mock) -> None:
    """A scheduler listed in exclude_entity_ids is skipped even though it is earliest (#64)."""
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1", "switch.schedule_2"])

    mock_state_1 = Mock()
    mock_state_1.state = "on"
    mock_state_1.attributes = {
        "next_trigger": "2024-01-15T08:00:00+01:00",
        "next_slot": 0,
        "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
    }

    mock_state_2 = Mock()
    mock_state_2.state = "on"
    mock_state_2.attributes = {
        "next_trigger": "2024-01-15T07:00:00+01:00",  # Earlier time, but excluded
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

    result = await reader.get_next_timeslot(exclude_entity_ids=frozenset({"switch.schedule_2"}))

    assert result is not None
    assert result.scheduler_entity == "switch.schedule_1"
    assert result.target_temp == 21.0


@pytest.mark.asyncio
async def test_get_next_timeslot_excluding_all_returns_none(mock_hass: Mock) -> None:
    """Excluding every configured scheduler yields no candidate, not an error."""
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1"])
    mock_state = _hacs_state(
        "switch.schedule_1",
        {
            "next_trigger": "2024-01-15T08:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
        },
    )
    mock_hass.states.get.return_value = mock_state

    result = await reader.get_next_timeslot(exclude_entity_ids=frozenset({"switch.schedule_1"}))

    assert result is None


@pytest.mark.asyncio
async def test_get_next_timeslot_default_exclude_matches_today_behavior(mock_hass: Mock) -> None:
    """Omitting exclude_entity_ids behaves exactly as before this feature (regression guard)."""
    reader = HASchedulerReader(mock_hass, ["switch.schedule_1"])
    mock_state = _hacs_state(
        "switch.schedule_1",
        {
            "next_trigger": "2024-01-15T08:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
        },
    )
    mock_hass.states.get.return_value = mock_state

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.scheduler_entity == "switch.schedule_1"


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


def _hacs_state(entity_id: str, attributes: dict) -> Mock:
    """Build an enabled HACS scheduler state with the given attributes."""
    state = Mock()
    state.entity_id = entity_id
    state.state = "on"
    state.attributes = attributes
    return state


def test_extract_from_next_entries_ignores_integer_indices(reader: HASchedulerReader) -> None:
    """scheduler-component publishes next_entries as timeslot indices (ints) (#189)."""
    attrs = {"next_entries": [0, 1, 2]}

    assert reader._extract_from_next_entries(attrs) == (None, None)


@pytest.mark.parametrize("entry", ["07:00", None, 1.5, ["time"]])
def test_extract_from_next_entries_ignores_non_dict_entries(
    reader: HASchedulerReader, entry: object
) -> None:
    """Any non-dict first entry is ignored instead of raising AttributeError."""
    assert reader._extract_from_next_entries({"next_entries": [entry]}) == (None, None)


def test_extract_from_next_entries_dict_entry_still_supported(reader: HASchedulerReader) -> None:
    """The legacy dict layout of next_entries keeps working."""
    attrs = {
        "next_entries": [
            {
                "time": "2024-01-15T07:00:00+01:00",
                "actions": [{"service": "climate.set_temperature", "data": {"temperature": 20.5}}],
            }
        ]
    }

    next_time, target_temp = reader._extract_from_next_entries(attrs)

    assert next_time == datetime.fromisoformat("2024-01-15T07:00:00+01:00")
    assert target_temp == 20.5


@pytest.mark.asyncio
async def test_get_next_timeslot_integer_next_entries_without_temperature(
    reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """A slot without resolvable temperature plus int next_entries is skipped, not a crash."""
    mock_hass.states.get.return_value = _hacs_state(
        "switch.heating_schedule",
        {
            "next_trigger": "2024-01-15T07:00:00+01:00",
            "next_slot": 0,
            "next_entries": [0, 1],
            "actions": [{"service": "climate.set_hvac_mode", "data": {"hvac_mode": "heat"}}],
        },
    )

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_get_next_timeslot_integer_next_entries_does_not_block_other_schedulers(
    mock_hass: Mock,
) -> None:
    """A scheduler with int next_entries and no temperature does not hide the others (#189)."""
    reader = HASchedulerReader(mock_hass, ["switch.unresolvable", "switch.valid"])
    states = {
        "switch.unresolvable": _hacs_state(
            "switch.unresolvable",
            {
                "next_trigger": "2024-01-15T06:00:00+01:00",
                "next_slot": 0,
                "next_entries": [0],
                "actions": [
                    {"service": "climate.set_preset_mode", "data": {"preset_mode": "unknown"}}
                ],
            },
        ),
        "switch.valid": _hacs_state(
            "switch.valid",
            {
                "next_trigger": "2024-01-15T07:00:00+01:00",
                "next_slot": 0,
                "next_entries": [0],
                "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
            },
        ),
    }
    mock_hass.states.get.side_effect = states.get

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.scheduler_entity == "switch.valid"
    assert result.target_temp == 21.0


@pytest.mark.asyncio
async def test_get_next_timeslot_isolates_unexpected_scheduler_error(
    mock_hass: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected error while reading one scheduler is logged and the others are still used."""
    reader = HASchedulerReader(mock_hass, ["switch.broken", "switch.valid"])
    broken_state = _hacs_state("switch.broken", {"friendly_name": "Broken"})
    valid_state = _hacs_state(
        "switch.valid",
        {
            "next_trigger": "2024-01-15T07:00:00+01:00",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": 21.0}}],
        },
    )
    mock_hass.states.get.side_effect = {
        "switch.broken": broken_state,
        "switch.valid": valid_state,
    }.get
    original_extract = reader._extract_timeslot_data

    def extract(state: Mock) -> tuple[datetime | None, float | None]:
        if state is broken_state:
            raise AttributeError("unexpected attribute layout")
        return original_extract(state)

    with (
        patch.object(reader, "_extract_timeslot_data", side_effect=extract),
        caplog.at_level(logging.WARNING),
    ):
        result = await reader.get_next_timeslot()

    assert result is not None
    assert result.scheduler_entity == "switch.valid"
    assert any(
        record.levelno == logging.WARNING and "Broken" in record.getMessage()
        for record in caplog.records
    )


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
        mock_hass, ["switch.schedule"], climate_entity_id="climate.test_vtherm"
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
        mock_hass, ["switch.schedule"], climate_entity_id="climate.test_vtherm"
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
# Native schedules are read through the blocks that ``schedule.get_schedule`` returns, so these
# tests give the mocked ``hass`` a schedule and a fixed "now" (a Monday at noon, Paris time).

NATIVE_ID = "schedule.planning_chauffage"
NATIVE_MODULE = (
    "custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader"
)
PARIS = ZoneInfo("Europe/Paris")
MONDAY_NOON = datetime(2024, 1, 15, 12, 0, tzinfo=PARIS)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _native_schedule(**by_day: list[dict]) -> dict:
    return {NATIVE_ID: {day: by_day.get(day, []) for day in WEEKDAYS}}


def _give_schedule(mock_hass: Mock, schedule: dict) -> None:
    mock_hass.services.async_call = AsyncMock(return_value=schedule)


async def _next_timeslot(reader: HASchedulerReader):
    with patch(f"{NATIVE_MODULE}.dt_util.now", return_value=MONDAY_NOON):
        return await reader.get_next_timeslot()


def _evening_block(data: dict | None = None) -> list[dict]:
    block = {"from": "18:00:00", "to": "22:00:00"}
    if data is not None:
        block["data"] = data
    return [block]


@pytest.fixture
def native_schedule_reader(mock_hass: Mock) -> HASchedulerReader:
    """Create a HASchedulerReader configured with a native HA schedule entity."""
    mock_hass.states.get.return_value = Mock(entity_id=NATIVE_ID, state="off", attributes={})
    mock_hass.is_running = True
    return HASchedulerReader(mock_hass, [NATIVE_ID])


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_next_block(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """The next block start is the slot to anticipate."""
    _give_schedule(mock_hass, _native_schedule(monday=_evening_block()))

    result = await _next_timeslot(native_schedule_reader)

    assert result is not None
    assert isinstance(result, ScheduledTimeslot)
    assert result.target_time == datetime(2024, 1, 15, 18, 0, tzinfo=PARIS)
    assert result.target_temp == 20.0  # Default temperature (no VTherm configured)
    assert result.timeslot_id.startswith("schedule.planning_chauffage_")


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_running_block_still_anticipates_the_next(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """A schedule that is ON is no longer skipped (it used to be, as next_event was its end).

    While a block runs, the next block's start is still anticipated, which includes a block
    that starts right when the running one ends.
    """
    mock_hass.states.get.return_value = Mock(entity_id=NATIVE_ID, state="on", attributes={})
    blocks = [{"from": "10:00:00", "to": "13:00:00"}, {"from": "13:00:00", "to": "16:00:00"}]
    _give_schedule(mock_hass, _native_schedule(monday=blocks))

    result = await _next_timeslot(native_schedule_reader)

    assert result is not None
    assert result.target_time == datetime(2024, 1, 15, 13, 0, tzinfo=PARIS)


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_without_blocks(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """A native schedule with no block has no next slot."""
    _give_schedule(mock_hass, _native_schedule())

    assert await _next_timeslot(native_schedule_reader) is None


def _make_vtherm_state(attributes: dict) -> Mock:
    """Create a VTherm climate state mock with the given attributes."""
    vtherm_state = Mock()
    vtherm_state.entity_id = "climate.vtherm"
    vtherm_state.state = "heat"
    vtherm_state.attributes = attributes
    return vtherm_state


def _native_reader_with_vtherm(
    mock_hass: Mock,
    vtherm_attributes: dict,
    blocks: list[dict] | None = None,
    settings: NativeScheduleSettings | None = None,
) -> HASchedulerReader:
    """Create a native schedule reader whose VTherm exposes ``vtherm_attributes``."""
    states = {
        NATIVE_ID: Mock(entity_id=NATIVE_ID, state="off", attributes={}),
        "climate.vtherm": _make_vtherm_state(vtherm_attributes),
    }
    mock_hass.states.get.side_effect = states.get
    mock_hass.is_running = True
    _give_schedule(mock_hass, _native_schedule(monday=blocks or _evening_block()))
    return HASchedulerReader(
        mock_hass, [NATIVE_ID], climate_entity_id="climate.vtherm", native_settings=settings
    )


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_targets_comfort_not_current_setpoint(
    mock_hass: Mock,
) -> None:
    """Regression #188: the OFF period setpoint must not be used as the slot target.

    While the schedule is off the VTherm holds its eco setpoint (17°C); the
    next ON slot applies the comfort preset (21°C), which is what IHP must
    anticipate.
    """
    reader = _native_reader_with_vtherm(
        mock_hass,
        {
            "temperature": 17.0,
            "preset_mode": "eco",
            "preset_temperatures": {"eco_temp": 17.0, "comfort_temp": 21.0},
        },
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 21.0


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_comfort_from_legacy_attribute(
    mock_hass: Mock,
) -> None:
    """The comfort preset is also read from legacy flat VTherm attributes."""
    reader = _native_reader_with_vtherm(
        mock_hass, {"temperature": 16.0, "preset_mode": "eco", "comfort_temp": 20.5}
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 20.5


@pytest.mark.asyncio
async def test_get_next_timeslot_native_schedule_without_comfort_uses_default(
    mock_hass: Mock,
) -> None:
    """Without a comfort preset, the default is used, never the current setpoint."""
    reader = _native_reader_with_vtherm(
        mock_hass,
        {
            "temperature": 17.0,
            "preset_mode": "eco",
            "preset_temperatures": {"eco_temp": 17.0, "comfort_temp": 0},
        },
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 20.0


VTHERM_PRESETS = {
    "temperature": 17.0,
    "preset_mode": "eco",
    "preset_temperatures": {"eco_temp": 17.0, "comfort_temp": 21.0, "boost_temp": 23.0},
}


@pytest.mark.asyncio
async def test_native_schedule_block_data_is_ignored_without_the_opt_in(mock_hass: Mock) -> None:
    """Unchanged without the opt-in: the target stays the comfort preset and no action is read."""
    reader = _native_reader_with_vtherm(
        mock_hass, VTHERM_PRESETS, _evening_block({"preset": "boost", "temperature": 19})
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 21.0
    assert result.action is None


@pytest.mark.asyncio
async def test_native_schedule_block_preset_gives_the_action_and_its_temperature(
    mock_hass: Mock,
) -> None:
    reader = _native_reader_with_vtherm(
        mock_hass,
        VTHERM_PRESETS,
        _evening_block({"preset": "boost"}),
        NativeScheduleSettings(drive_enabled=True),
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.action == SlotAction(preset="boost")
    assert result.target_temp == 23.0  # the boost preset's temperature, for the calculation


@pytest.mark.asyncio
async def test_native_schedule_block_temperature_is_the_target(mock_hass: Mock) -> None:
    reader = _native_reader_with_vtherm(
        mock_hass,
        VTHERM_PRESETS,
        _evening_block({"temperature": 19.5}),
        NativeScheduleSettings(drive_enabled=True),
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.action == SlotAction(temperature=19.5)
    assert result.target_temp == 19.5


@pytest.mark.asyncio
async def test_native_schedule_preset_wins_and_the_block_temperature_feeds_the_calculation(
    mock_hass: Mock,
) -> None:
    reader = _native_reader_with_vtherm(
        mock_hass,
        VTHERM_PRESETS,
        _evening_block({"preset": "boost", "temperature": 22.0}),
        NativeScheduleSettings(drive_enabled=True),
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.action == SlotAction(preset="boost", temperature=22.0)
    assert result.target_temp == 22.0


@pytest.mark.asyncio
async def test_native_schedule_block_without_data_gets_the_fallback_preset(mock_hass: Mock) -> None:
    reader = _native_reader_with_vtherm(
        mock_hass, VTHERM_PRESETS, None, NativeScheduleSettings(drive_enabled=True)
    )

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.action == SlotAction(preset="comfort")
    assert result.target_temp == 21.0


async def test_is_scheduler_enabled_native_schedule_off_state_is_enabled(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled returns True for an existing OFF native schedule.

    Native HA schedules are considered enabled when the entity exists,
    even when their state is "off" (which just means outside an active timeslot).
    """
    mock_state = Mock()
    mock_state.state = "off"
    mock_hass.states.get.return_value = mock_state

    result = await native_schedule_reader.is_scheduler_enabled("schedule.planning_chauffage")

    assert result is True
    mock_hass.states.get.assert_called_once_with("schedule.planning_chauffage")


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
    mock_hass.states.get.assert_called_once_with("schedule.planning_chauffage")


@pytest.mark.asyncio
async def test_is_scheduler_enabled_native_schedule_entity_not_found(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled returns False when the schedule entity does not exist."""
    mock_hass.states.get.return_value = None

    result = await native_schedule_reader.is_scheduler_enabled("schedule.planning_chauffage")

    assert result is False
    mock_hass.states.get.assert_called_once_with("schedule.planning_chauffage")


@pytest.mark.asyncio
async def test_is_scheduler_enabled_native_schedule_unavailable(
    native_schedule_reader: HASchedulerReader, mock_hass: Mock
) -> None:
    """Test that is_scheduler_enabled returns False when the schedule entity is unavailable."""
    mock_state = Mock()
    mock_state.state = "unavailable"
    mock_hass.states.get.return_value = mock_state

    result = await native_schedule_reader.is_scheduler_enabled("schedule.planning_chauffage")

    assert result is False


def test_get_native_schedule_temperature_no_vtherm_uses_default(
    reader: HASchedulerReader,
) -> None:
    """Without a VTherm entity, the default comfort temperature is returned."""
    result = reader._native_target_temperature(None)

    assert result == 20.0


def test_get_native_schedule_temperature_vtherm_missing_uses_default(mock_hass: Mock) -> None:
    """An unavailable VTherm entity falls back to the default comfort temperature."""
    mock_hass.states.get.return_value = None
    reader = HASchedulerReader(mock_hass, ["schedule.test"], climate_entity_id="climate.vtherm")

    result = reader._native_target_temperature(None)

    assert result == 20.0


def test_get_native_schedule_temperature_flat_comfort_zero_uses_default(
    mock_hass: Mock,
) -> None:
    """A flat ``comfort_temp`` of 0 is an uninitialized preset, like in preset_temperatures."""
    mock_hass.states.get.return_value = _make_vtherm_state(
        {
            "temperature": 17.0,
            "preset_mode": "eco",
            "preset_temperatures": {"comfort_temp": 0},
            "comfort_temp": 0,
        }
    )
    reader = HASchedulerReader(mock_hass, ["schedule.test"], climate_entity_id="climate.vtherm")

    result = reader._native_target_temperature(None)

    assert result == 20.0


def test_get_native_schedule_temperature_comfort_active_uses_current_target(
    mock_hass: Mock,
) -> None:
    """When comfort is the active preset, its current target is the comfort value."""
    mock_hass.states.get.return_value = _make_vtherm_state(
        {"temperature": 21.5, "preset_mode": "comfort"}
    )
    reader = HASchedulerReader(mock_hass, ["schedule.test"], climate_entity_id="climate.vtherm")

    result = reader._native_target_temperature(None)

    assert result == 21.5


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

    # Native schedule: its next block starts at 07:00 on Monday
    native_state = Mock()
    native_state.entity_id = "schedule.native_schedule"
    native_state.state = "off"
    native_state.attributes = {"friendly_name": "Native Schedule"}
    mock_hass.services.async_call = AsyncMock(
        return_value={
            "schedule.native_schedule": {
                day: ([{"from": "07:00:00", "to": "09:00:00"}] if day == "monday" else [])
                for day in WEEKDAYS
            }
        }
    )

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

    now = datetime(2024, 1, 15, 5, 0, tzinfo=PARIS)
    with patch(f"{NATIVE_MODULE}.dt_util.now", return_value=now):
        result = await reader.get_next_timeslot()

    # Should pick the earlier native schedule timeslot
    assert result is not None
    assert result.scheduler_entity == "schedule.native_schedule"


# ── Climate Scheduler (switch.* owned by climate_scheduler) tests ─────────────

CS_ID = "switch.living_room_plan"


class _Owner:
    """Resolves every entity to a fixed kind, so tests need no entity registry."""

    def __init__(self, kind) -> None:
        self._kind = kind

    def resolve(self, _entity_id: str):
        return self._kind


def _cs_state(state: str, actions: list, next_slot: int) -> Mock:
    return Mock(
        entity_id=CS_ID,
        state=state,
        attributes={
            "next_trigger": "2024-01-15T18:00:00+01:00",
            "next_slot": next_slot,
            "actions": actions,
        },
    )


def _cs_reader(mock_hass: Mock, state: Mock, vtherm_attributes: dict | None = None):
    from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind

    states = {CS_ID: state, "climate.vtherm": _make_vtherm_state(vtherm_attributes or {})}
    mock_hass.states.get.side_effect = states.get
    mock_hass.is_running = True
    return HASchedulerReader(
        mock_hass,
        [CS_ID],
        climate_entity_id="climate.vtherm",
        ownership_resolver=_Owner(SchedulerKind.CLIMATE_SCHEDULER),
    )


def _cs_temp(entity: str, value: float) -> dict:
    return {
        "entity_id": entity,
        "service": "climate.set_temperature",
        "data": {"temperature": value},
    }


@pytest.mark.asyncio
async def test_a_climate_scheduler_switch_gives_its_nodes_temperature_and_action(
    mock_hass: Mock,
) -> None:
    actions = [_cs_temp("climate.other", 16.0), _cs_temp("climate.vtherm", 17.0)]
    reader = _cs_reader(mock_hass, _cs_state("on", actions, 0))

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.target_temp == 17.0  # our climate's entry, not the other room's
    assert result.action == SlotAction(temperature=17.0)
    assert result.scheduler_entity == CS_ID


@pytest.mark.asyncio
async def test_a_climate_scheduler_preset_node_gives_the_preset_temperature(
    mock_hass: Mock,
) -> None:
    node = {
        "entity_id": "climate.vtherm",
        "service": "climate.set_preset_mode",
        "data": {"preset_mode": "boost"},
    }
    reader = _cs_reader(
        mock_hass,
        _cs_state("on", [node], 0),
        {"preset_temperatures": {"boost_temp": 23.0}},
    )

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.action == SlotAction(preset="boost")
    assert result.target_temp == 23.0


@pytest.mark.asyncio
async def test_a_disabled_climate_scheduler_switch_is_skipped(mock_hass: Mock) -> None:
    reader = _cs_reader(mock_hass, _cs_state("off", [_cs_temp("climate.vtherm", 21.0)], 0))

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_a_climate_scheduler_node_without_an_action_gives_no_slot(mock_hass: Mock) -> None:
    node = {
        "entity_id": "climate.vtherm",
        "service": "climate.set_temperature",
        "data": {"temperature": None},
    }
    reader = _cs_reader(mock_hass, _cs_state("on", [node], 0))

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_without_a_resolver_a_switch_is_read_as_a_hacs_scheduler(mock_hass: Mock) -> None:
    """Unchanged for existing setups: the HACS reading has no action and trusts actions[next_slot]."""
    states = {CS_ID: _cs_state("on", [_cs_temp("climate.other", 16.0)], 0)}
    mock_hass.states.get.side_effect = states.get
    mock_hass.is_running = True
    reader = HASchedulerReader(mock_hass, [CS_ID])

    result = await reader.get_next_timeslot()

    assert result is not None
    assert result.target_temp == 16.0
    assert result.action is None


def _generic_climate_native_reader(
    mock_hass: Mock, mapping: dict[str, float] | None
) -> HASchedulerReader:
    """Create a native schedule reader over a generic climate that lists presets only (#252)."""
    # Only the state of the climate and of the schedule is needed from this helper
    _native_reader_with_vtherm(
        mock_hass, {"temperature": 17.0, "preset_mode": "eco", "preset_modes": ["eco", "comfort"]}
    )
    return HASchedulerReader(
        mock_hass,
        [NATIVE_ID],
        climate_entity_id="climate.vtherm",
        preset_resolver=HAPresetTemperatureResolver(mock_hass, "climate.vtherm", mapping),
    )


@pytest.mark.asyncio
async def test_native_schedule_on_a_generic_climate_uses_the_mapped_comfort_temperature(
    mock_hass: Mock,
) -> None:
    """The comfort preset of a climate that publishes no temperature is the one the user mapped."""
    reader = _generic_climate_native_reader(mock_hass, {"comfort": 21.5})

    result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 21.5


@pytest.mark.asyncio
async def test_native_schedule_on_a_generic_climate_without_mapping_warns_and_uses_default(
    mock_hass: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Without a mapping the default is used, and the log says which preset is unknown."""
    reader = _generic_climate_native_reader(mock_hass, None)

    with caplog.at_level(logging.WARNING):
        result = await _next_timeslot(reader)

    assert result is not None
    assert result.target_temp == 20.0
    assert any("comfort" in record.getMessage() for record in caplog.records)
