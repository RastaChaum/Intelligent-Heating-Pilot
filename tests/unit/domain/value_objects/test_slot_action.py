"""Unit tests for the SlotAction value object (what a slot asks of the climate)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.slot_action import (
    SlotAction,
    SlotActionKind,
)


def test_a_preset_slot_is_applied_as_a_preset() -> None:
    action = SlotAction(preset="comfort")

    assert action.applied_kind is SlotActionKind.PRESET


def test_a_temperature_slot_is_applied_as_a_temperature() -> None:
    action = SlotAction(temperature=21.0)

    assert action.applied_kind is SlotActionKind.TEMPERATURE


def test_the_preset_wins_when_both_are_given() -> None:
    """The preset is applied; the temperature only feeds the anticipation calculation."""
    action = SlotAction(preset="comfort", temperature=21.0)

    assert action.applied_kind is SlotActionKind.PRESET
    assert action.temperature == 21.0


def test_an_empty_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SlotAction()


@pytest.mark.parametrize("preset", ["", "   "])
def test_a_blank_preset_is_rejected(preset: str) -> None:
    with pytest.raises(ValueError, match="preset"):
        SlotAction(preset=preset)


@pytest.mark.parametrize("temperature", [math.nan, math.inf, -math.inf])
def test_a_non_finite_temperature_is_rejected(temperature: float) -> None:
    with pytest.raises(ValueError, match="temperature"):
        SlotAction(temperature=temperature)


def test_the_action_is_immutable() -> None:
    action = SlotAction(preset="eco")

    with pytest.raises(dataclasses.FrozenInstanceError):
        action.preset = "comfort"  # type: ignore[misc]
