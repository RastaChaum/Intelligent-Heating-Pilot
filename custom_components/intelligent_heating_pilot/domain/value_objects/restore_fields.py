"""Restore fields value object: what to write back to a climate entity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RestoreFields:
    """The only values IHP writes back when it undoes a preheat.

    The HVAC mode is deliberately absent: IHP never changes it, so it never restores it.

    Attributes:
        preset: Preset mode to select again, if the climate had one.
        temperature: Target temperature to set again, only when there was no preset.
    """

    preset: str | None = None
    temperature: float | None = None

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to write back."""
        return self.preset is None and self.temperature is None
