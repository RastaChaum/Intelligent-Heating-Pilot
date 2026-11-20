"""Reading the preset to temperature mapping a user stored in the options (#252)."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def parse_preset_temperatures(stored: Any) -> dict[str, float]:
    """Turn the stored mapping into {preset: temperature}, dropping what cannot be read.

    A hand-edited or older entry must never prevent a device from loading, so an unreadable
    value only loses its own preset.

    Args:
        stored: The value held by the config entry, normally a dict of numbers.

    Returns:
        The readable part of the mapping; empty when there is none.
    """
    if not isinstance(stored, dict):
        return {}
    mapping: dict[str, float] = {}
    for preset, value in stored.items():
        try:
            mapping[str(preset)] = float(value)
        except (TypeError, ValueError):
            _LOGGER.warning("Ignoring the temperature mapped to preset '%s': %r", preset, value)
    return mapping
