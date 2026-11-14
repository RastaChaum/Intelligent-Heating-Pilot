"""Native Home Assistant schedule reader.

A native ``schedule.*`` helper does not say what its blocks mean: each block may carry free
``data`` that the user filled in, with no convention on the keys. The entity only exposes that
data for the block that is running, so the next block is read through the ``schedule.get_schedule``
service, which returns every block with its data.

This adapter only translates what the service returns; it holds no heating rule.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, NamedTuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.value_objects.slot_action import SlotAction

_LOGGER = logging.getLogger(__name__)

SCHEDULE_DOMAIN = "schedule"
SERVICE_GET_SCHEDULE = "get_schedule"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Today plus the seven following days: the same weekday next week must be reachable.
DAYS_TO_SCAN = 8


@dataclass(frozen=True)
class NativeScheduleSettings:
    """How IHP reads and uses native schedule blocks, per IHP instance.

    Attributes:
        drive_enabled: Whether IHP applies the next block's action itself. Block ``data`` is
            read only when this is on; off, the schedule is computed only, as before.
        preset_key: Block data key that holds a preset name.
        temperature_key: Block data key that holds a target temperature.
        fallback_preset: Preset used when a block has neither key. It also stands in for the
            temperature of a block when the calculation needs one.
    """

    drive_enabled: bool = False
    preset_key: str = "preset"
    temperature_key: str = "temperature"
    fallback_preset: str = "comfort"

    def __post_init__(self) -> None:
        """Validate the settings.

        Raises:
            ValueError: If a key or the fallback preset is blank.
        """
        for field in ("preset_key", "temperature_key", "fallback_preset"):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} cannot be blank")


class NativeSlot(NamedTuple):
    """The next block of a native schedule.

    Attributes:
        start: When the block starts (timezone-aware).
        action: What the block applies; None when IHP does not drive native schedules.
    """

    start: datetime
    action: SlotAction | None


class HANativeScheduleReader:
    """Reads the next block of a native schedule helper."""

    def __init__(self, hass: HomeAssistant, settings: NativeScheduleSettings) -> None:
        """Initialize the reader.

        Args:
            hass: Home Assistant instance.
            settings: How blocks are read and used.
        """
        self._hass = hass
        self._settings = settings

    async def next_slot(self, entity_id: str) -> NativeSlot | None:
        """Return the next block start of a native schedule.

        The next *start* is returned whatever the schedule's state: while a block runs, its end
        is not a start, but the start of the block that follows it, even an adjacent one, is.

        Args:
            entity_id: The ``schedule.*`` entity id.

        Returns:
            The next block, or None when there is none or the schedule cannot be read.
        """
        schedule = await self._fetch(entity_id)
        if not schedule:
            return None
        now = dt_util.now()
        found = self._earliest_future_block(schedule, now)
        if found is None:
            return None
        start, data = found
        return NativeSlot(start=start, action=self._action_from(data))

    async def _fetch(self, entity_id: str) -> dict[str, Any] | None:
        try:
            response = await self._hass.services.async_call(
                SCHEDULE_DOMAIN,
                SERVICE_GET_SCHEDULE,
                {"entity_id": entity_id},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - one unreadable schedule must not block the others
            _LOGGER.debug("Could not read schedule %s", entity_id, exc_info=True)
            return None
        schedule = response.get(entity_id) if isinstance(response, dict) else None
        return schedule if isinstance(schedule, dict) else None

    def _earliest_future_block(
        self, schedule: dict[str, Any], now: datetime
    ) -> tuple[datetime, dict[str, Any]] | None:
        for offset in range(DAYS_TO_SCAN):
            day = now.date() + timedelta(days=offset)
            starts = [
                parsed
                for block in schedule.get(WEEKDAYS[day.weekday()]) or []
                if (parsed := self._parse_block(block, day, now.tzinfo)) is not None
                and parsed[0] > now
            ]
            if starts:
                return min(starts, key=lambda item: item[0])
        return None

    @staticmethod
    def _parse_block(
        block: Any, day: date, tz: tzinfo | None
    ) -> tuple[datetime, dict[str, Any]] | None:
        if not isinstance(block, dict):
            return None
        start_time = _as_time(block.get("from"))
        if start_time is None:
            return None
        data = block.get("data")
        return datetime.combine(day, start_time, tzinfo=tz), data if isinstance(data, dict) else {}

    def _action_from(self, data: dict[str, Any]) -> SlotAction | None:
        """Turn a block's data into the action to apply, when IHP drives native schedules."""
        if not self._settings.drive_enabled:
            return None
        preset = _as_preset(data.get(self._settings.preset_key))
        temperature = _as_temperature(data.get(self._settings.temperature_key))
        if preset is None and temperature is None:
            return SlotAction(preset=self._settings.fallback_preset)
        return SlotAction(preset=preset, temperature=temperature)


def _as_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return dt_util.parse_time(value)
    return None


def _as_preset(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_temperature(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        temperature = float(value.strip() if isinstance(value, str) else value)
    except (TypeError, ValueError):
        return None
    return temperature if math.isfinite(temperature) else None
