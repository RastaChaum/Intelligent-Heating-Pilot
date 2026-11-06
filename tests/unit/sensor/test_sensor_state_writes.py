"""Unit tests for when IHP sensors write their state to Home Assistant (issue #191).

An anticipation event must be written whenever the sensor value or one of its
attributes changes, exactly once, and never when nothing changed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.sensor import (
    IntelligentHeatingPilotAnticipationTimeSensor,
    IntelligentHeatingPilotContextualLearnedSlopeSensor,
    IntelligentHeatingPilotDeadTimeSensor,
    IntelligentHeatingPilotNextScheduleSensor,
    IntelligentHeatingPilotSensorBase,
)

ENTRY_ID = "test_entry_state_writes"
DEVICE_NAME = "Test IHP"
CONTEXTUAL_LHS = 1.5


def _event_data(**overrides: object) -> dict:
    """Return a complete anticipation event payload for our config entry."""
    data = {
        "entry_id": ENTRY_ID,
        "anticipated_start_time": "2026-01-15T06:30:00+00:00",
        "next_schedule_time": "2026-01-15T07:00:00+00:00",
        "next_target_temperature": 20.0,
        "anticipation_minutes": 30.0,
        "current_temp": 18.0,
        "learned_heating_slope": 2.0,
        "confidence_level": 0.8,
        "scheduler_entity": "switch.schedule_living_room",
    }
    data.update(overrides)
    return data


def _event(**overrides: object) -> Mock:
    """Return an HA-like event carrying an anticipation payload."""
    return Mock(data=_event_data(**overrides))


@pytest.fixture
def config_entry() -> Mock:
    """Create a mock config entry."""
    entry = Mock()
    entry.entry_id = ENTRY_ID
    return entry


@pytest.fixture
def coordinator() -> Mock:
    """Create a coordinator mock with a learned contextual slope."""
    coord = Mock()
    coord.get_contextual_learned_heating_slope = Mock(return_value=CONTEXTUAL_LHS)
    coord.get_effective_dead_time = AsyncMock(return_value=None)
    return coord


def _with_write_spy(sensor: IntelligentHeatingPilotSensorBase) -> Mock:
    """Replace the HA state write with a spy and return it."""
    spy = Mock()
    sensor.async_write_ha_state = spy  # type: ignore[method-assign]
    return spy


@pytest.mark.parametrize(
    ("sensor_class", "attribute_change"),
    [
        (IntelligentHeatingPilotAnticipationTimeSensor, {"current_temp": 18.5}),
        (IntelligentHeatingPilotAnticipationTimeSensor, {"confidence_level": 0.9}),
        (IntelligentHeatingPilotNextScheduleSensor, {"next_target_temperature": 21.0}),
        (IntelligentHeatingPilotNextScheduleSensor, {"scheduler_entity": "switch.other"}),
    ],
)
def test_attribute_only_change_is_written(
    sensor_class: type[IntelligentHeatingPilotSensorBase],
    attribute_change: dict,
    coordinator: Mock,
    config_entry: Mock,
) -> None:
    """An attribute change with an unchanged timestamp still reaches HA."""
    sensor = sensor_class(coordinator, config_entry, DEVICE_NAME)
    write = _with_write_spy(sensor)
    sensor._handle_anticipation_event(_event())
    write.reset_mock()

    sensor._handle_anticipation_event(_event(**attribute_change))

    write.assert_called_once()


def test_identical_event_is_not_written(coordinator: Mock, config_entry: Mock) -> None:
    """Nothing changed: no state write."""
    sensor = IntelligentHeatingPilotAnticipationTimeSensor(coordinator, config_entry, DEVICE_NAME)
    write = _with_write_spy(sensor)
    sensor._handle_anticipation_event(_event())
    write.reset_mock()

    sensor._handle_anticipation_event(_event())

    write.assert_not_called()


def test_contextual_sensor_writes_once_on_schedule_change(
    coordinator: Mock, config_entry: Mock
) -> None:
    """The contextual sensor manages its own writes, so the base must not write again."""
    sensor = IntelligentHeatingPilotContextualLearnedSlopeSensor(
        coordinator, config_entry, DEVICE_NAME
    )
    write = _with_write_spy(sensor)

    sensor._handle_anticipation_event(_event())

    write.assert_called_once()


def test_cleared_message_logged_only_on_transition(
    coordinator: Mock, config_entry: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Repeated empty slots must not log a "cleared" message at INFO each time."""
    sensor = IntelligentHeatingPilotNextScheduleSensor(coordinator, config_entry, DEVICE_NAME)
    _with_write_spy(sensor)
    sensor._handle_anticipation_event(_event())

    with caplog.at_level(logging.INFO):
        for _ in range(3):
            sensor._handle_anticipation_event(_event(next_schedule_time=None))

    cleared = [r for r in caplog.records if "cleared" in r.getMessage()]
    assert len(cleared) == 1


def test_scheduler_blocked_attributes_exposed_when_populated(
    coordinator: Mock, config_entry: Mock
) -> None:
    """Issue #64: a successful fallback still reports which scheduler was blocked."""
    sensor = IntelligentHeatingPilotAnticipationTimeSensor(coordinator, config_entry, DEVICE_NAME)
    _with_write_spy(sensor)

    sensor._handle_anticipation_event(
        _event(scheduler_blocked=False, blocked_schedulers=["switch.non_vacation"])
    )

    assert sensor.extra_state_attributes["scheduler_blocked"] is False
    assert sensor.extra_state_attributes["blocked_schedulers"] == ["switch.non_vacation"]


def test_scheduler_blocked_attributes_survive_when_anticipation_cleared(
    coordinator: Mock, config_entry: Mock
) -> None:
    """Issue #64: when every scheduler is blocked, anticipated_start_time is None but
    the household must still see scheduler_blocked/blocked_schedulers, not an empty dict."""
    sensor = IntelligentHeatingPilotAnticipationTimeSensor(coordinator, config_entry, DEVICE_NAME)
    _with_write_spy(sensor)

    sensor._handle_anticipation_event(
        _event(
            anticipated_start_time=None,
            scheduler_blocked=True,
            blocked_schedulers=["switch.a", "switch.b"],
        )
    )

    assert sensor.native_value is None
    assert sensor.extra_state_attributes["scheduler_blocked"] is True
    assert sensor.extra_state_attributes["blocked_schedulers"] == ["switch.a", "switch.b"]


def test_dead_time_sensor_shares_device_info(coordinator: Mock, config_entry: Mock) -> None:
    """All sensors register the same device, so they must describe it identically."""
    dead_time = IntelligentHeatingPilotDeadTimeSensor(coordinator, config_entry, DEVICE_NAME)
    anticipation = IntelligentHeatingPilotAnticipationTimeSensor(
        coordinator, config_entry, DEVICE_NAME
    )

    assert dead_time.device_info == anticipation.device_info
    assert dead_time.device_info["name"] == DEVICE_NAME


def test_next_schedule_time_parsed_from_event(coordinator: Mock, config_entry: Mock) -> None:
    """Sanity check: the next schedule sensor exposes the event timestamp."""
    sensor = IntelligentHeatingPilotNextScheduleSensor(coordinator, config_entry, DEVICE_NAME)
    _with_write_spy(sensor)

    sensor._handle_anticipation_event(_event())

    assert sensor.native_value == datetime.fromisoformat("2026-01-15T07:00:00+00:00")
