"""Fake ports for the actuator tests: a climate that reacts to commands, and an in-memory store."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IClimateCommander,
    IPreheatRecordStore,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ClimateSnapshot,
    PreheatRecord,
    RestoreFields,
    ScheduledTimeslot,
    SlotAction,
)

NOW = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
SLOT_TIME = NOW + timedelta(hours=2)
PRESETS = ("eco", "comfort", "boost")


def make_snapshot(**overrides) -> ClimateSnapshot:
    values = {
        "hvac_mode": "heat",
        "preset": "eco",
        "temperature": 18.0,
        "available_presets": PRESETS,
    }
    values.update(overrides)
    return ClimateSnapshot(**values)


def make_timeslot(
    action: SlotAction | None = None,
    slot_id: str = "switch.plan_slot",
    slot_time: datetime = SLOT_TIME,
    scheduler: str = "switch.plan",
) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=slot_time,
        target_temp=21.0,
        timeslot_id=slot_id,
        scheduler_entity=scheduler,
        action=SlotAction(preset="comfort") if action is None else action,
    )


class FakeClimate:
    """A climate that applies commands, unless told to ignore them or to apply them late."""

    def __init__(self, snapshot: ClimateSnapshot | None = None) -> None:
        self.snapshot: ClimateSnapshot | None = snapshot or make_snapshot()
        self.ignore_commands = False
        self.apply_on_next_wait = False
        self.pending: SlotAction | None = None
        self.waits = 0

    def read_climate_snapshot(self) -> ClimateSnapshot | None:
        return self.snapshot

    async def wait_for_state_change(self, timeout_seconds: float) -> bool:
        self.waits += 1
        if self.apply_on_next_wait and self.pending is not None:
            self._take(self.pending)
            self.pending = None
            return True
        await asyncio.sleep(min(timeout_seconds, 0.001))
        return False

    def _take(self, action: SlotAction) -> None:
        assert self.snapshot is not None
        if action.preset is not None:
            self.snapshot = replace(self.snapshot, preset=action.preset)
        else:
            self.snapshot = replace(self.snapshot, preset="none", temperature=action.temperature)


class FakeCommander(IClimateCommander):
    def __init__(self, climate: FakeClimate, events: list[str]) -> None:
        self._climate = climate
        self._events = events
        self.applied: list[SlotAction] = []
        self.restored: list[RestoreFields] = []

    async def apply(self, action: SlotAction) -> None:
        self._events.append("apply")
        self.applied.append(action)
        await asyncio.sleep(0)  # a real service call yields: lets a second start run meanwhile
        if self._climate.ignore_commands:
            return
        if self._climate.apply_on_next_wait:
            self._climate.pending = action
            return
        self._climate._take(action)

    async def restore(self, fields: RestoreFields) -> None:
        self._events.append("restore")
        self.restored.append(fields)


class FakeStore(IPreheatRecordStore):
    def __init__(self, events: list[str]) -> None:
        self.record: PreheatRecord | None = None
        self._events = events
        self.saves = 0

    async def load(self) -> PreheatRecord | None:
        return self.record

    async def save(self, record: PreheatRecord) -> None:
        self._events.append("save")
        self.saves += 1
        self.record = record

    async def clear(self) -> None:
        self._events.append("clear")
        self.record = None
