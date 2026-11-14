"""Climate Scheduler reader.

Climate Scheduler exposes switches that imitate HACS Scheduler's attributes, but not quite with
the same meaning: ``next_slot`` is the index of a *node*, while ``actions`` holds one entry per
node and per scheduled entity. Reading ``actions[next_slot]`` is only right for a single entity;
for a group it can be another room's action. This adapter picks the entry of IHP's own climate.

It only translates attributes into a start time and a slot action; it holds no heating rule.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ...domain.value_objects.slot_action import SlotAction

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_PRESET_MODE = "climate.set_preset_mode"
SERVICE_SET_TEMPERATURE = "climate.set_temperature"
# Climate Scheduler writes this when it cannot name the entity of a single-entity schedule
UNKNOWN_ENTITY = "unknown"


class HAClimateSchedulerReader:
    """Reads the next node of a Climate Scheduler switch for one climate entity."""

    def __init__(self, climate_entity_id: str) -> None:
        """Initialize the reader.

        Args:
            climate_entity_id: The climate entity IHP preheats; its node entry is the one read.
        """
        self._climate_entity_id = climate_entity_id

    def read(self, attributes: Mapping[str, Any]) -> tuple[datetime | None, SlotAction | None]:
        """Read the next node's start and action from a switch's attributes.

        A node that keeps the current setpoint ("no change") or only changes the HVAC mode
        applies nothing to anticipate, so it gives no action.

        Args:
            attributes: The state attributes of the Climate Scheduler switch.

        Returns:
            Tuple of (start, action); either is None when it cannot be read.
        """
        start = self._parse_start(attributes.get("next_trigger"))
        node = self._next_node_entry(attributes)
        return start, self._to_action(node)

    @staticmethod
    def _parse_start(raw: Any) -> datetime | None:
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw))
        if parsed is None:
            _LOGGER.debug("Could not parse next_trigger: %s", raw)
            return None
        return parsed if parsed.tzinfo is not None else dt_util.as_local(parsed)

    def _next_node_entry(self, attributes: Mapping[str, Any]) -> dict[str, Any] | None:
        """Pick the entry of our climate for the next node among all nodes' entries."""
        actions = attributes.get("actions")
        next_slot = attributes.get("next_slot")
        if (
            not isinstance(actions, list)
            or not isinstance(next_slot, int)
            or isinstance(next_slot, bool)
        ):
            return None
        entries = [entry for entry in actions if isinstance(entry, dict)]
        ours = [entry for entry in entries if entry.get("entity_id") == self._climate_entity_id]
        if not ours and {entry.get("entity_id") for entry in entries} <= {UNKNOWN_ENTITY}:
            ours = entries  # a single schedule whose entity Climate Scheduler could not name
        if not 0 <= next_slot < len(ours):
            return None
        return ours[next_slot]

    @staticmethod
    def _to_action(entry: dict[str, Any] | None) -> SlotAction | None:
        if entry is None:
            return None
        data = entry.get("data")
        if not isinstance(data, dict):
            return None
        service = entry.get("service")
        if service == SERVICE_SET_PRESET_MODE:
            preset = data.get("preset_mode")
            return (
                SlotAction(preset=preset.strip())
                if isinstance(preset, str) and preset.strip()
                else None
            )
        if service == SERVICE_SET_TEMPERATURE:
            temperature = data.get("temperature")
            if isinstance(temperature, bool) or not isinstance(temperature, int | float):
                return None
            return (
                SlotAction(temperature=float(temperature)) if math.isfinite(temperature) else None
            )
        return None
