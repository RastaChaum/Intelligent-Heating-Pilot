"""Combined timeslot reader: the schedulers' slots and the wake-up sources' deadlines as one.

Consumers of ``ISchedulerReader`` (the calculation, the decision strategies, the use cases) ask
for "the next slot". With wake-up sources there are two kinds of candidates, and the earliest
valid one wins, whatever its origin: this class answers that question, so that none of the
consumers has to know sources exist.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from ...domain.constants import DEFAULT_PRESET_TEMPERATURE_C
from ...domain.interfaces.climate_data_reader_interface import IClimateDataReader
from ...domain.interfaces.preheat_record_store_interface import IPreheatRecordStore
from ...domain.interfaces.preset_temperature_resolver_interface import IPresetTemperatureResolver
from ...domain.interfaces.schedule_slot_lookup_interface import IScheduleSlotLookup
from ...domain.interfaces.scheduler_reader_interface import ISchedulerReader
from ...domain.interfaces.wake_up_source_reader_interface import IWakeUpSourceReader
from ...domain.services.wake_up_deadline_policy import WakeUpDeadlinePolicy
from ...domain.services.wake_up_target_policy import WakeUpTargetPolicy
from ...domain.value_objects.scheduled_timeslot import ScheduledTimeslot
from ...domain.value_objects.slot_action import SlotAction
from ...domain.value_objects.wake_up_source_config import WakeUpSourceConfig

_LOGGER = logging.getLogger(__name__)


class CombinedTimeslotReader(ISchedulerReader):
    """Gives the earliest valid deadline among the schedulers and the wake-up sources.

    At the same instant the scheduler's slot wins, so that a single target applies. The
    identity of a source's slot is its entity and the local date of its deadline, not the time:
    a snooze keeps it, so that a change somebody else made to the thermostat stays theirs.
    """

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        source_reader: IWakeUpSourceReader,
        sources: Sequence[WakeUpSourceConfig],
        preset_resolver: IPresetTemperatureResolver,
        now: Callable[[], datetime],
        deadline_policy: WakeUpDeadlinePolicy | None = None,
        slot_lookup: IScheduleSlotLookup | None = None,
        climate_reader: IClimateDataReader | None = None,
        record_store: IPreheatRecordStore | None = None,
        target_policy: WakeUpTargetPolicy | None = None,
    ) -> None:
        """Initialize the reader.

        Args:
            scheduler_reader: Reads the schedulers' slots.
            source_reader: Reads the point in time held by a source entity.
            sources: The wake-up sources of this IHP.
            preset_resolver: Tells the temperature a preset stands for.
            now: Current time, timezone-aware.
            deadline_policy: Judges whether a reading is a usable deadline.
            slot_lookup: Tells the schedule slots around a moment, for a source whose target
                comes from the schedule. Without it every target is the fixed one.
            climate_reader: Gives the thermostat's current target, the reference the schedule's
                target is compared with.
            record_store: Gives the record of a running preheat, whose earlier target is that
                reference while the preheat runs: the current one is then IHP's own.
            target_policy: Chooses between the fixed target and the schedule's.
        """
        self._schedulers = scheduler_reader
        self._source_reader = source_reader
        self._sources = {source.entity_id: source for source in sources}
        self._preset_resolver = preset_resolver
        self._now = now
        self._policy = deadline_policy or WakeUpDeadlinePolicy()
        self._lookup = slot_lookup
        self._climate = climate_reader
        self._records = record_store
        self._target_policy = target_policy or WakeUpTargetPolicy()
        self._announced: str | None = None
        self._ignored_warned: set[str] = set()

    async def get_next_timeslot(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> ScheduledTimeslot | None:
        """Retrieve the earliest valid deadline among schedulers and sources.

        Args:
            exclude_entity_ids: Entities to skip for this call.

        Returns:
            The earliest slot, the scheduler's one on a tie, or None when there is none.
        """
        scheduler_slot = await self._schedulers.get_next_timeslot(exclude_entity_ids)
        source_slots = [
            slot
            for entity_id in self._sources
            if entity_id not in exclude_entity_ids
            and (slot := await self._source_slot(entity_id)) is not None
        ]
        earliest_source = min(source_slots, key=lambda slot: slot.target_time, default=None)
        if earliest_source is None:
            return scheduler_slot
        if scheduler_slot is not None and scheduler_slot.target_time <= earliest_source.target_time:
            return scheduler_slot
        self._announce(earliest_source)
        return earliest_source

    def is_wake_up_source(self, entity_id: str) -> bool:
        """Tell whether an entity is one of this IHP's wake-up sources.

        Args:
            entity_id: The entity that owns a slot.

        Returns:
            True for a configured source.
        """
        return entity_id in self._sources

    async def get_next_scheduler_timeslot(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> ScheduledTimeslot | None:
        """Retrieve the next timeslot of the schedulers alone, wake-up sources left out.

        Args:
            exclude_entity_ids: Scheduler entity ids to skip for this call.

        Returns:
            The next scheduler timeslot, or None when there is none.
        """
        return await self._schedulers.get_next_timeslot(exclude_entity_ids)

    async def is_scheduler_enabled(self, scheduler_entity_id: str) -> bool:
        """Tell whether a scheduler is enabled, or a source currently gives a deadline.

        Args:
            scheduler_entity_id: A scheduler or a source entity.

        Returns:
            For a source, True while it gives a valid deadline.
        """
        if scheduler_entity_id in self._sources:
            return await self._source_slot(scheduler_entity_id) is not None
        return await self._schedulers.is_scheduler_enabled(scheduler_entity_id)

    async def get_next_timeslot_of(self, scheduler_entity_id: str) -> ScheduledTimeslot | None:
        """Retrieve the next slot of one scheduler or one source.

        Args:
            scheduler_entity_id: A scheduler or a source entity.

        Returns:
            Its slot, or None when it has none.
        """
        if scheduler_entity_id in self._sources:
            return await self._source_slot(scheduler_entity_id)
        return await self._schedulers.get_next_timeslot_of(scheduler_entity_id)

    async def _source_slot(self, entity_id: str) -> ScheduledTimeslot | None:
        """Build the slot of a source, or None when it gives no usable deadline."""
        config = self._sources[entity_id]
        now = self._now()
        deadline = self._policy.judge(self._source_reader.read(entity_id), now, config.horizon)
        if deadline is None:
            return None
        slot_id = f"{entity_id}_{deadline.astimezone(now.tzinfo).date().isoformat()}"
        action = await self._target_of(config, deadline, slot_id)
        if action is None:
            self._warn_ignored_once(entity_id, slot_id)
            return None
        self._ignored_warned.discard(entity_id)
        return ScheduledTimeslot(
            target_time=deadline,
            target_temp=self._temperature_of(action),
            timeslot_id=slot_id,
            scheduler_entity=entity_id,
            action=action,
            hold=config.hold,
        )

    async def _target_of(
        self, config: WakeUpSourceConfig, deadline: datetime, slot_id: str
    ) -> SlotAction | None:
        """Choose the target of a source: its fixed one, or the schedule's when asked to."""
        if not config.target_from_schedule or self._lookup is None:
            return config.fixed_target
        slots = await self._lookup.get_slots_around(deadline)
        reference = await self._reference_target(config.entity_id, slot_id)
        return self._target_policy.resolve(config, slots, reference)

    async def _reference_target(self, entity_id: str, slot_id: str) -> float | None:
        """Give the target the schedule's is compared with: the one before IHP acted.

        While a preheat runs for this wake-up, the thermostat's current target is the one IHP
        set: comparing with it would flip the choice mid-preheat. The recorded earlier target
        is what the room would have without IHP.
        """
        if self._records is not None:
            record = await self._records.load()
            if record is not None and record.timeslot_id == slot_id:
                return record.previous.temperature
        snapshot = self._climate.read_climate_snapshot() if self._climate is not None else None
        return snapshot.temperature if snapshot is not None else None

    def _temperature_of(self, action: SlotAction) -> float:
        """Give the temperature the anticipation heads for, whatever the action names."""
        if action.temperature is not None:
            return action.temperature
        resolved = self._preset_resolver.resolve(action.preset) if action.preset else None
        return resolved if resolved is not None else DEFAULT_PRESET_TEMPERATURE_C

    def _warn_ignored_once(self, entity_id: str, slot_id: str) -> None:
        """Say once per wake-up why a source with a deadline is ignored."""
        if slot_id in self._ignored_warned:
            return
        self._ignored_warned.add(slot_id)
        _LOGGER.warning(
            "Wake-up source %s is ignored: it has a deadline but no usable target (the schedule "
            "cannot tell and no fixed preset or temperature is set)",
            entity_id,
        )

    def _announce(self, slot: ScheduledTimeslot) -> None:
        """Say once per wake-up that a source drives the next deadline."""
        if self._announced == slot.timeslot_id:
            return
        self._announced = slot.timeslot_id
        _LOGGER.info(
            "Wake-up source %s sets the next deadline at %s (%.1f°C)",
            slot.scheduler_entity,
            slot.target_time.strftime("%H:%M"),
            slot.target_temp,
        )
