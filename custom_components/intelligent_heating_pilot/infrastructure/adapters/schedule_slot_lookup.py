"""Home Assistant schedule slot lookup.

Implements IScheduleSlotLookup over the schedulers of one IHP. A native schedule can say what
runs at any moment, because ``schedule.get_schedule`` gives every block. HACS Scheduler and
Climate Scheduler only publish their next trigger: the slot that follows a moment is known only
when that trigger is after it, and the slot in effect is never guessed (a weekly schedule differs
from day to day, so the previous node says nothing).

It translates attributes into slots; the choice between them is a domain rule.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...domain.interfaces.preset_temperature_resolver_interface import IPresetTemperatureResolver
from ...domain.interfaces.schedule_slot_lookup_interface import IScheduleSlotLookup
from ...domain.interfaces.scheduler_ownership_resolver_interface import ISchedulerOwnershipResolver
from ...domain.value_objects import ScheduledTimeslot, SchedulerKind, SlotAction, SlotsAround
from .chauffage_reader import HAChauffageReader
from .climate_scheduler_reader import HAClimateSchedulerReader
from .native_schedule_reader import HANativeScheduleReader, NativeBlock
from .utils import get_entity_name

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_PRESET_MODE = "climate.set_preset_mode"
SERVICE_SET_TEMPERATURE = "climate.set_temperature"


class HAScheduleSlotLookup(IScheduleSlotLookup):
    """Tells which schedule slots surround a moment, for every kind of scheduler."""

    def __init__(
        self,
        hass: HomeAssistant,
        scheduler_entity_ids: list[str],
        ownership_resolver: ISchedulerOwnershipResolver,
        native_reader: HANativeScheduleReader,
        climate_scheduler_reader: HAClimateSchedulerReader,
        preset_resolver: IPresetTemperatureResolver,
    ) -> None:
        """Initialize the lookup.

        Args:
            hass: Home Assistant instance.
            scheduler_entity_ids: The schedulers of the IHP.
            ownership_resolver: Tells which integration owns a scheduler.
            native_reader: Reads native schedule blocks.
            climate_scheduler_reader: Reads Climate Scheduler nodes.
            preset_resolver: Tells the temperature a preset stands for.
        """
        self._hass = hass
        self._scheduler_ids = scheduler_entity_ids
        self._resolver = ownership_resolver
        self._native = native_reader
        self._climate_scheduler = climate_scheduler_reader
        self._chauffage = HAChauffageReader()
        self._presets = preset_resolver

    async def get_slots_around(self, moment: datetime) -> SlotsAround:
        """Tell the schedule slots around a moment, over all configured schedulers.

        Args:
            moment: The moment, timezone-aware.

        Returns:
            The most recent slot in effect and the earliest following one that could be told.
        """
        in_effect: list[ScheduledTimeslot] = []
        following: list[ScheduledTimeslot] = []
        for entity_id in self._scheduler_ids:
            try:
                around = await self._around(entity_id, moment)
            except Exception:  # noqa: BLE001 - one unreadable scheduler must not block the others
                _LOGGER.warning(
                    "[%s] Could not read the slots around %s, skipping this scheduler",
                    get_entity_name(self._hass, entity_id),
                    moment.isoformat(),
                    exc_info=True,
                )
                continue
            if around.in_effect is not None:
                in_effect.append(around.in_effect)
            if around.following is not None:
                following.append(around.following)
        return SlotsAround(
            in_effect=max(in_effect, key=lambda slot: slot.target_time, default=None),
            following=min(following, key=lambda slot: slot.target_time, default=None),
        )

    async def _around(self, entity_id: str, moment: datetime) -> SlotsAround:
        kind = self._resolver.resolve(entity_id)
        if kind is SchedulerKind.NATIVE:
            return await self._native_around(entity_id, moment)
        if kind in (SchedulerKind.HACS, SchedulerKind.CLIMATE_SCHEDULER, SchedulerKind.CHAUFFAGE):
            return self._next_trigger_around(entity_id, kind, moment)
        return SlotsAround()

    async def _native_around(self, entity_id: str, moment: datetime) -> SlotsAround:
        in_effect, following = await self._native.blocks_around(entity_id, moment)
        return SlotsAround(
            in_effect=self._slot_of_block(entity_id, in_effect),
            following=self._slot_of_block(entity_id, following),
        )

    def _slot_of_block(self, entity_id: str, block: NativeBlock | None) -> ScheduledTimeslot | None:
        if block is None:
            return None
        return self._slot(entity_id, block.start, self._native.block_action(block.data))

    def _next_trigger_around(
        self, entity_id: str, kind: SchedulerKind, moment: datetime
    ) -> SlotsAround:
        """Read the next trigger: it follows the moment only if nothing lies in between."""
        state = self._hass.states.get(entity_id)
        if state is None or state.state == "off":
            return SlotsAround()
        if kind is SchedulerKind.CLIMATE_SCHEDULER:
            start, action = self._climate_scheduler.read(state.attributes)
        elif kind is SchedulerKind.CHAUFFAGE:
            start, action = self._chauffage.read(state)
        else:
            start, action = _hacs_next(state.attributes)
        if start is None or start <= moment:
            return SlotsAround()
        return SlotsAround(following=self._slot(entity_id, start, action))

    def _slot(
        self, entity_id: str, start: datetime, action: SlotAction | None
    ) -> ScheduledTimeslot | None:
        """Build a slot, or None when its temperature cannot be told: it could not be compared."""
        if action is None:
            return None
        temperature = action.temperature
        if temperature is None and action.preset is not None:
            temperature = self._presets.resolve(action.preset)
        if temperature is None:
            return None
        return ScheduledTimeslot(
            target_time=start,
            target_temp=temperature,
            timeslot_id=f"{entity_id}_{start.isoformat()}",
            scheduler_entity=entity_id,
            action=action,
        )


def _hacs_next(attributes: Mapping[str, Any]) -> tuple[datetime | None, SlotAction | None]:
    """Read HACS Scheduler's next trigger and the action it runs for the climate."""
    raw = attributes.get("next_trigger")
    start = dt_util.parse_datetime(str(raw)) if raw else None
    if start is not None and start.tzinfo is None:
        start = dt_util.as_local(start)
    actions = attributes.get("actions")
    next_slot = attributes.get("next_slot")
    if (
        not isinstance(actions, list)
        or not isinstance(next_slot, int)
        or isinstance(next_slot, bool)
    ):
        return start, None
    if not 0 <= next_slot < len(actions):
        return start, None
    return start, _hacs_action(actions[next_slot])


def _hacs_action(entry: Any) -> SlotAction | None:
    if not isinstance(entry, dict):
        return None
    service = entry.get("service") or entry.get("service_call")
    data = entry.get("data") or entry.get("service_data") or {}
    if service == SERVICE_SET_PRESET_MODE:
        preset = data.get("preset_mode") or data.get("preset") or data.get("mode")
        return (
            SlotAction(preset=preset.strip())
            if isinstance(preset, str) and preset.strip()
            else None
        )
    if service == SERVICE_SET_TEMPERATURE:
        temperature = data.get("temperature")
        try:
            return SlotAction(temperature=float(temperature)) if temperature is not None else None
        except (TypeError, ValueError):
            return None
    return None
