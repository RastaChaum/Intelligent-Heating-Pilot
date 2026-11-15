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
from ...domain.interfaces.preset_temperature_resolver_interface import IPresetTemperatureResolver
from ...domain.interfaces.scheduler_reader_interface import ISchedulerReader
from ...domain.interfaces.wake_up_source_reader_interface import IWakeUpSourceReader
from ...domain.services.wake_up_deadline_policy import WakeUpDeadlinePolicy
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
    ) -> None:
        """Initialize the reader.

        Args:
            scheduler_reader: Reads the schedulers' slots.
            source_reader: Reads the point in time held by a source entity.
            sources: The wake-up sources of this IHP.
            preset_resolver: Tells the temperature a preset stands for.
            now: Current time, timezone-aware.
            deadline_policy: Judges whether a reading is a usable deadline.
        """
        self._schedulers = scheduler_reader
        self._source_reader = source_reader
        self._sources = {source.entity_id: source for source in sources}
        self._preset_resolver = preset_resolver
        self._now = now
        self._policy = deadline_policy or WakeUpDeadlinePolicy()
        self._announced: str | None = None

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
        action = await self._target_of(config, deadline)
        if action is None:
            _LOGGER.debug("Wake-up source %s has no usable target, ignored", entity_id)
            return None
        return ScheduledTimeslot(
            target_time=deadline,
            target_temp=self._temperature_of(action),
            timeslot_id=f"{entity_id}_{deadline.astimezone(now.tzinfo).date().isoformat()}",
            scheduler_entity=entity_id,
            action=action,
            hold=config.hold,
        )

    async def _target_of(self, config: WakeUpSourceConfig, deadline: datetime) -> SlotAction | None:
        """Choose the target of a source: its fixed one, until the schedule rules are added."""
        return config.fixed_target

    def _temperature_of(self, action: SlotAction) -> float:
        """Give the temperature the anticipation heads for, whatever the action names."""
        if action.temperature is not None:
            return action.temperature
        resolved = self._preset_resolver.resolve(action.preset) if action.preset else None
        return resolved if resolved is not None else DEFAULT_PRESET_TEMPERATURE_C

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
