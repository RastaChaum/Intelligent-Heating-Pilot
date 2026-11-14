"""Slot action value object: what a scheduler slot asks of the climate entity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class SlotActionKind(Enum):
    """How a slot action is applied to the climate entity."""

    PRESET = "preset"
    TEMPERATURE = "temperature"


@dataclass(frozen=True)
class SlotAction:
    """The action a slot applies: a preset, a temperature, or both.

    A preset slot must be applied as a preset and a temperature slot as a temperature, never
    the other way round: setting a temperature on a thermostat leaves its preset mode and
    disables the handling tied to that mode. When a slot carries both, the preset is applied
    and the temperature only feeds the anticipation calculation.

    Attributes:
        preset: Preset mode name, when the slot sets one.
        temperature: Target temperature in Celsius, when the slot gives one.
    """

    preset: str | None = None
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Validate that the action is usable.

        Raises:
            ValueError: If neither field is set, the preset is blank, or the temperature
                is not a finite number.
        """
        if self.preset is None and self.temperature is None:
            raise ValueError("A slot action needs at least one of preset or temperature")
        if self.preset is not None and not self.preset.strip():
            raise ValueError("A slot action preset cannot be blank")
        if self.temperature is not None and not math.isfinite(self.temperature):
            raise ValueError("A slot action temperature must be a finite number")

    @property
    def applied_kind(self) -> SlotActionKind:
        """How the action is applied: the preset wins when both are given."""
        if self.preset is not None:
            return SlotActionKind.PRESET
        return SlotActionKind.TEMPERATURE
