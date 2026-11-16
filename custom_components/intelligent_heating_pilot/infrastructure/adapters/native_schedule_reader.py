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
END_OF_DAY = "24:00"


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


class NativeBlock(NamedTuple):
    """One block of a native schedule on a given day: when it runs and what it carries."""

    start: datetime
    end: datetime
    data: dict[str, Any]


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
        self._legacy_warned = False

    async def next_slot(self, entity_id: str) -> NativeSlot | None:
        """Return the next block start of a native schedule.

        The next *start* is returned whatever the schedule's state: while a block runs, its end
        is not a start, but the start of the block that follows it, even an adjacent one, is.

        Args:
            entity_id: The ``schedule.*`` entity id.

        Returns:
            The next block, or None when there is none or the schedule cannot be read.
        """
        if not self._hass.services.has_service(SCHEDULE_DOMAIN, SERVICE_GET_SCHEDULE):
            return self._next_slot_from_attributes(entity_id)
        schedule = await self._fetch(entity_id)
        if not schedule:
            return None
        now = dt_util.now()
        found = self._earliest_future_block(schedule, now)
        if found is None:
            return None
        start, data = found
        return NativeSlot(start=start, action=self._action_from(data))

    async def blocks_around(
        self, entity_id: str, moment: datetime
    ) -> tuple[NativeBlock | None, NativeBlock | None]:
        """Return the block in effect at a moment and the first block starting after it.

        Needs ``schedule.get_schedule`` (Home Assistant 2025.3): the helper's attributes say
        nothing about a block that is not running. Without it, nothing is known.

        Args:
            entity_id: The ``schedule.*`` entity id.
            moment: The moment, timezone-aware.

        Returns:
            Tuple of (block in effect, block that follows); either is None when there is none
            or the schedule cannot be read.
        """
        if not self._hass.services.has_service(SCHEDULE_DOMAIN, SERVICE_GET_SCHEDULE):
            return None, None
        schedule = await self._fetch(entity_id)
        if not schedule:
            return None, None
        blocks = self._blocks_over(schedule, moment)
        in_effect = [block for block in blocks if block.start <= moment < block.end]
        following = [block for block in blocks if block.start > moment]
        return (
            max(in_effect, key=lambda block: block.start, default=None),
            min(following, key=lambda block: block.start, default=None),
        )

    def _blocks_over(self, schedule: dict[str, Any], moment: datetime) -> list[NativeBlock]:
        """List the blocks of the days around a moment, one entry per day they run."""
        blocks: list[NativeBlock] = []
        for offset in range(-1, DAYS_TO_SCAN):
            day = moment.date() + timedelta(days=offset)
            for raw in schedule.get(WEEKDAYS[day.weekday()]) or []:
                block = self._block_on(raw, day, moment.tzinfo)
                if block is not None:
                    blocks.append(block)
        return blocks

    @staticmethod
    def _block_on(raw: Any, day: date, tz: tzinfo | None) -> NativeBlock | None:
        parsed = HANativeScheduleReader._parse_block(raw, day, tz)
        if parsed is None or not isinstance(raw, dict):
            return None
        end = HANativeScheduleReader._end_of(raw.get("to"), day, tz)
        if end is None:
            return None
        if end <= parsed[0]:  # a block that ends at midnight ends the next day
            end += timedelta(days=1)
        return NativeBlock(parsed[0], end, parsed[1])

    @staticmethod
    def _end_of(value: Any, day: date, tz: tzinfo | None) -> datetime | None:
        """Read a block's end; "24:00:00" is the end of the day, which is no valid time."""
        if isinstance(value, str) and value.startswith(END_OF_DAY):
            return datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
        end_time = _as_time(value)
        return datetime.combine(day, end_time, tzinfo=tz) if end_time is not None else None

    def block_action(self, data: dict[str, Any]) -> SlotAction | None:
        """Turn a block's data into an action, whether or not IHP drives native schedules.

        A block that carries neither key gives no action: unlike a driven schedule, there is no
        fallback preset to stand in, since the action would be used as a target.
        """
        preset = _as_preset(data.get(self._settings.preset_key))
        temperature = _as_temperature(data.get(self._settings.temperature_key))
        if preset is None and temperature is None:
            return None
        return SlotAction(preset=preset, temperature=temperature)

    def _next_slot_from_attributes(self, entity_id: str) -> NativeSlot | None:
        """Read the next ON block from the entity's ``next_event`` attribute.

        Home Assistant only offers ``schedule.get_schedule`` from 2025.3. Before that, the
        helper tells only when its next event happens: the next ON time while it is off, the
        next OFF time while it is on. So nothing is anticipated while a block runs, a block's
        data cannot be read, and a driven schedule gets the fallback preset.
        """
        if not self._legacy_warned:
            self._legacy_warned = True
            _LOGGER.warning(
                "Home Assistant has no schedule.get_schedule service (it needs 2025.3): native "
                "schedules are read from their next event only, so block data is not available"
            )
        state = self._hass.states.get(entity_id)
        if state is None or state.state != "off":
            return None
        start = self._parse_event(state.attributes.get("next_event"))
        if start is None:
            return None
        action = (
            SlotAction(preset=self._settings.fallback_preset)
            if self._settings.drive_enabled
            else None
        )
        return NativeSlot(start=start, action=action)

    @staticmethod
    def _parse_event(value: Any) -> datetime | None:
        parsed = (
            value
            if isinstance(value, datetime)
            else (dt_util.parse_datetime(str(value)) if value else None)
        )
        if parsed is None:
            return None
        return parsed if parsed.tzinfo is not None else dt_util.as_local(parsed)

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
