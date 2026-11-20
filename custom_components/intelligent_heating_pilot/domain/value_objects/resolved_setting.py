"""The effective value of a setting and where it came from (#302)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SettingSource(Enum):
    """Where an effective value comes from."""

    OVERRIDE = "override"
    CENTRAL = "central"
    DEFAULT = "default"


@dataclass(frozen=True)
class ResolvedSetting:
    """One setting after applying override, then central value, then built-in default.

    Attributes:
        key: A catalog key.
        value: The effective value; ``None`` is "none" for an optional setting.
        source: Which of the three levels supplied it.
    """

    key: str
    value: object | None
    source: SettingSource
