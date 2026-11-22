"""ha-chauffage "Next change" sensor reader.

ha-chauffage publishes, on each thermostat's device, a sensor whose state is the time of the next
change and whose attributes are named like a ``climate`` entity's: ``hvac_mode``, ``preset_mode``,
``temperature``. They are what Chauffage will send, so IHP can pass them to the ``climate``
services as they are. During an override the state is the end of the override.

It only translates a state into a start time and a slot action; it holds no heating rule.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from ...domain.value_objects.slot_action import SlotAction

_LOGGER = logging.getLogger(__name__)

# The only mode IHP preheats for: it heats, it never cools
HEATING_HVAC_MODE = "heat"
# States of the sensor that mean "no slot to preheat"
NO_SLOT_STATES = frozenset({"unknown", "unavailable", "none", ""})


class HAChauffageReader:
    """Reads the next change of a ha-chauffage "Next change" sensor."""

    def read(self, state: State) -> tuple[datetime | None, SlotAction | None]:
        """Read the next change's start and action.

        A change that is not in ``heat`` mode gives no action: IHP only heats. The preset wins
        over the temperature when both are given, the temperature then only tells what the
        preset gives.

        Args:
            state: The state of the sensor.

        Returns:
            Tuple of (start, action); either is None when it cannot be read.
        """
        start = self._parse_start(state.state)
        if start is None:
            return None, None
        return start, self._to_action(state.attributes)

    @staticmethod
    def _parse_start(raw: str) -> datetime | None:
        if raw.strip().lower() in NO_SLOT_STATES:
            return None
        parsed = dt_util.parse_datetime(raw)
        if parsed is None:
            _LOGGER.debug("Could not parse the next change: %s", raw)
            return None
        return parsed if parsed.tzinfo is not None else dt_util.as_local(parsed)

    @staticmethod
    def _to_action(attributes: Mapping[str, Any]) -> SlotAction | None:
        hvac_mode = attributes.get("hvac_mode")
        if not isinstance(hvac_mode, str) or hvac_mode.strip().lower() != HEATING_HVAC_MODE:
            return None
        preset = attributes.get("preset_mode")
        preset = preset.strip() if isinstance(preset, str) and preset.strip() else None
        temperature = attributes.get("temperature")
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, int | float)
            or not math.isfinite(temperature)
        ):
            temperature = None
        if preset is None and temperature is None:
            return None
        return SlotAction(
            preset=preset, temperature=None if temperature is None else float(temperature)
        )
