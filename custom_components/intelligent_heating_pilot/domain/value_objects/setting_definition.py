"""Description of one configurable setting of an IHP device (#302)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SettingScope(Enum):
    """Whether a setting can be inherited from the central configuration."""

    DEVICE = "device"
    SHAREABLE = "shareable"


class SettingTheme(Enum):
    """The group of related settings shown together as one form."""

    THERMOSTAT_SCHEDULERS = "thermostat_schedulers"
    NATIVE_SCHEDULE = "native_schedule"
    WAKE_UP_SOURCES = "wake_up_sources"
    ENVIRONMENT = "environment"
    LEARNING = "learning"
    CYCLE_DETECTION = "cycle_detection"
    ANTICIPATION = "anticipation"
    PRESET_TEMPERATURES = "preset_temperatures"


@dataclass(frozen=True)
class SettingDefinition:
    """One declared setting.

    The definition is the single place that says which form a setting belongs to, whether a
    device may inherit it and what its built-in default is; the forms derive everything else
    from it, so a new setting is one entry here plus its labels.

    Attributes:
        key: The stored key, unique in the catalog.
        theme: The form the setting appears in.
        scope: ``DEVICE`` (never inherited) or ``SHAREABLE``.
        default: The built-in default; ``None`` for optional entities and device settings.
        optional: True when "none" is a valid value (the environment sensors).
    """

    key: str
    theme: SettingTheme
    scope: SettingScope
    default: object | None = None
    optional: bool = False

    def __post_init__(self) -> None:
        """Validate the definition.

        Raises:
            ValueError: If the key is empty.
        """
        if not self.key:
            raise ValueError("A setting needs a non-empty key")
