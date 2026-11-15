"""Tests for HAWakeUpSourceReader: a state becomes a reading, never an exception."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import ReadingIssue
from custom_components.intelligent_heating_pilot.infrastructure.adapters.wake_up_source_reader import (
    HAWakeUpSourceReader,
)

MODULE = "custom_components.intelligent_heating_pilot.infrastructure.adapters.wake_up_source_reader"


def _reader(entity_id: str, state: str | None, attributes: dict | None = None):
    hass = Mock()
    if state is None:
        hass.states.get.return_value = None
    else:
        hass.states.get.return_value = Mock(state=state, attributes=attributes or {})
    return HAWakeUpSourceReader(hass), entity_id


def test_timestamp_sensor_with_offset() -> None:
    reader, entity = _reader("sensor.alarm", "2026-11-16T05:30:00+00:00")
    reading = reader.read(entity)
    assert reading.value == datetime(2026, 11, 16, 5, 30, tzinfo=UTC)
    assert reading.issue is None


def test_datetime_entity() -> None:
    reader, entity = _reader("datetime.wake", "2026-11-16T05:30:00+01:00")
    assert reader.read(entity).value is not None


def test_input_datetime_with_date_and_time_is_read_in_the_local_zone() -> None:
    reader, entity = _reader(
        "input_datetime.wake",
        "2026-11-16 05:30:00",
        {"has_date": True, "has_time": True},
    )
    value = reader.read(entity).value
    assert value is not None and value.tzinfo is not None
    assert (value.hour, value.minute) == (5, 30)


@pytest.mark.parametrize(
    "attributes", [{"has_date": False, "has_time": True}, {"has_date": True, "has_time": False}]
)
def test_input_datetime_that_is_not_a_full_datetime_is_refused(attributes: dict) -> None:
    reader, entity = _reader("input_datetime.wake", "2026-11-16", attributes)
    assert reader.read(entity).issue is ReadingIssue.NOT_A_FULL_DATETIME


@pytest.mark.parametrize("state", ["2026-11-16", "05:30:00"])
def test_date_only_and_time_only_sensor_values_are_refused(state: str) -> None:
    reader, entity = _reader("sensor.alarm", state)
    assert reader.read(entity).issue is ReadingIssue.NOT_A_FULL_DATETIME


@pytest.mark.parametrize(
    ("state", "issue"),
    [
        ("unknown", ReadingIssue.UNKNOWN),
        ("", ReadingIssue.UNKNOWN),
        ("unavailable", ReadingIssue.UNAVAILABLE),
        ("tomorrow morning", ReadingIssue.UNPARSABLE),
    ],
)
def test_unusable_states(state: str, issue: ReadingIssue) -> None:
    reader, entity = _reader("sensor.alarm", state)
    assert reader.read(entity).issue is issue


def test_missing_entity_is_unavailable() -> None:
    reader, entity = _reader("sensor.alarm", None)
    assert reader.read(entity).issue is ReadingIssue.UNAVAILABLE


def test_a_bad_value_is_reported_once_until_it_changes(caplog: pytest.LogCaptureFixture) -> None:
    reader, entity = _reader("sensor.alarm", "tomorrow morning")
    with caplog.at_level(logging.WARNING, logger=MODULE):
        reader.read(entity)
        reader.read(entity)
        reader.read(entity)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    reader._hass.states.get.return_value = Mock(state="later", attributes={})
    with caplog.at_level(logging.WARNING, logger=MODULE):
        reader.read(entity)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_a_valid_value_clears_the_memory_of_the_issue(caplog: pytest.LogCaptureFixture) -> None:
    reader, entity = _reader("sensor.alarm", "later")
    with caplog.at_level(logging.WARNING, logger=MODULE):
        reader.read(entity)
        reader._hass.states.get.return_value = Mock(
            state="2026-11-16T05:30:00+00:00", attributes={}
        )
        reader.read(entity)
        reader._hass.states.get.return_value = Mock(state="later", attributes={})
        reader.read(entity)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2
