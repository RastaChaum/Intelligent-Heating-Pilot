"""Unit tests for HAChauffageReader: the next change of a ha-chauffage "Next change" sensor."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import SlotAction
from custom_components.intelligent_heating_pilot.infrastructure.adapters.chauffage_reader import (
    HAChauffageReader,
)

NEXT_CHANGE = "2026-11-16T18:00:00+01:00"


def _read(state: str = NEXT_CHANGE, **attributes):
    attrs = {"hvac_mode": "heat", "preset_mode": None, "temperature": None, **attributes}
    return HAChauffageReader().read(Mock(state=state, attributes=attrs))


def test_the_state_is_the_start_of_the_change() -> None:
    start, _ = _read(temperature=21.0)

    assert start is not None
    assert (start.hour, start.minute, start.utcoffset().total_seconds()) == (18, 0, 3600)


def test_a_preset_change_is_a_preset_action() -> None:
    _, action = _read(preset_mode="comfort")

    assert action == SlotAction(preset="comfort")


def test_a_temperature_change_is_a_temperature_action() -> None:
    _, action = _read(temperature=21.5)

    assert action == SlotAction(temperature=21.5)


def test_the_preset_wins_and_keeps_the_temperature_it_gives() -> None:
    _, action = _read(preset_mode="comfort", temperature=20.5)

    assert action == SlotAction(preset="comfort", temperature=20.5)
    assert action.preset == "comfort"


@pytest.mark.parametrize("mode", ["off", "cool", "heat_cool", None, 3])
def test_a_change_that_is_not_heating_gives_no_action(mode) -> None:
    start, action = _read(hvac_mode=mode, preset_mode="comfort")

    assert start is not None
    assert action is None


@pytest.mark.parametrize("state", ["unknown", "unavailable", "", "not a time"])
def test_a_state_that_is_not_a_time_gives_no_slot(state: str) -> None:
    assert _read(state=state, preset_mode="comfort") == (None, None)


def test_a_change_with_neither_preset_nor_temperature_gives_no_action() -> None:
    _, action = _read()

    assert action is None


@pytest.mark.parametrize("temperature", [True, "21", float("nan"), float("inf")])
def test_an_unusable_temperature_is_ignored(temperature) -> None:
    _, action = _read(preset_mode="comfort", temperature=temperature)

    assert action == SlotAction(preset="comfort")


def test_a_blank_preset_is_ignored() -> None:
    _, action = _read(preset_mode="  ", temperature=21.0)

    assert action == SlotAction(temperature=21.0)
