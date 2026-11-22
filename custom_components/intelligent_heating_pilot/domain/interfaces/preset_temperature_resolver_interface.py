"""Preset temperature resolver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IPresetTemperatureResolver(ABC):
    """Contract for telling which temperature a preset of the thermostat stands for.

    The anticipation needs a temperature even when a slot only names a preset, and the target
    of a wake-up source is compared with others through it.
    """

    @abstractmethod
    def resolve(self, preset: str) -> float | None:
        """Return the temperature the thermostat publishes for a preset.

        Args:
            preset: Preset mode name.

        Returns:
            The temperature in Celsius, or None when the thermostat does not publish it.
        """
