"""Climate snapshot value object: the requested state of a climate entity at one moment."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import TARGET_TEMP_MATCH_TOLERANCE_C
from .slot_action import SlotAction, SlotActionKind

NO_PRESET_NAME = "none"


def is_real_preset(preset: str | None) -> bool:
    """Return True for a preset that is actually active (not absent, not ``none``).

    Args:
        preset: Preset mode name, or None.

    Returns:
        True when the name designates a preset the user or a scheduler selected.
    """
    return preset is not None and preset.strip().lower() != NO_PRESET_NAME


@dataclass(frozen=True)
class ClimateSnapshot:
    """The state a user or a scheduler asked of a climate entity.

    The values are the *requested* ones where the entity publishes them: safety, power
    shedding, window or presence handling can change the visible preset or target without
    anybody asking, and a comparison on those would mistake them for a change by someone else.

    Attributes:
        hvac_mode: Requested HVAC mode; ``off`` means somebody stopped the climate.
        preset: Requested preset mode, if any.
        temperature: Requested target temperature in Celsius, if known.
        available_presets: Preset modes the entity offers.
    """

    hvac_mode: str
    preset: str | None = None
    temperature: float | None = None
    available_presets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the snapshot.

        Raises:
            ValueError: If the HVAC mode is blank.
        """
        if not self.hvac_mode or not self.hvac_mode.strip():
            raise ValueError("A climate snapshot needs an hvac_mode")

    def matches(self, action: SlotAction) -> bool:
        """Tell whether this state is the one the action asks for.

        Args:
            action: The action that was applied.

        Returns:
            True when the preset (for a preset action) or the temperature (for a temperature
            action) is already the requested one; an unknown temperature never matches.
        """
        if action.applied_kind is SlotActionKind.PRESET:
            return (
                self.preset is not None
                and action.preset is not None
                and self.preset.lower() == action.preset.lower()
            )
        if self.temperature is None or action.temperature is None:
            return False
        return abs(self.temperature - action.temperature) <= TARGET_TEMP_MATCH_TOLERANCE_C

    def offers_preset(self, preset: str) -> bool:
        """Tell whether the entity offers a preset, whatever its case.

        Args:
            preset: Preset mode name to look for.

        Returns:
            True when the preset is one of the available presets.
        """
        wanted = preset.lower()
        return any(wanted == available.lower() for available in self.available_presets)
