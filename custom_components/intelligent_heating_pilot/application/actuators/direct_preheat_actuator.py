"""Direct preheat actuator: applies the slot's own action to the climate and undoes it safely.

It composes ports and a pure policy, and imports nothing from Home Assistant: the climate is
read and written through ``IClimateDataReader`` and ``IClimateCommander``, the previous state
is kept through ``IPreheatRecordStore``, and every rule comes from ``PreheatSessionPolicy``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from time import monotonic

from ...domain.constants import ACTION_EFFECT_TIMEOUT_SECONDS
from ...domain.interfaces.climate_commander_interface import IClimateCommander
from ...domain.interfaces.climate_data_reader_interface import IClimateDataReader
from ...domain.interfaces.preheat_actuator_interface import IPreheatActuator
from ...domain.interfaces.preheat_record_store_interface import IPreheatRecordStore
from ...domain.services.preheat_session_policy import ApplyDecision, PreheatSessionPolicy
from ...domain.value_objects.actuation_result import ActuationResult
from ...domain.value_objects.cancel_reason import CancelReason
from ...domain.value_objects.climate_snapshot import ClimateSnapshot
from ...domain.value_objects.preheat_record import PreheatRecord
from ...domain.value_objects.restore_decision import RestoreDecision
from ...domain.value_objects.scheduled_timeslot import ScheduledTimeslot
from ...domain.value_objects.slot_action import SlotAction

_LOGGER = logging.getLogger(__name__)

_APPLY_DECISION_TO_RESULT: dict[ApplyDecision, ActuationResult] = {
    ApplyDecision.SKIP_OFF: ActuationResult.SKIPPED,
    ApplyDecision.SKIP_PRESET_UNAVAILABLE: ActuationResult.NOT_APPLIED,
    ApplyDecision.SKIP_ALREADY_APPLIED: ActuationResult.APPLIED,
}


class DirectPreheatActuator(IPreheatActuator):
    """Starts a preheat by applying the slot's action directly to the climate entity.

    The previous state is recorded once per slot, before the first write, so that a retry or
    a restart never records IHP's own state as the earlier one. A lock serializes starts and
    cancellations: the timer and a recalculation can reach the same slot at once.
    """

    def __init__(
        self,
        commander: IClimateCommander,
        climate_reader: IClimateDataReader,
        record_store: IPreheatRecordStore,
        policy: PreheatSessionPolicy,
        now: Callable[[], datetime],
        effect_timeout_seconds: float = ACTION_EFFECT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the actuator.

        Args:
            commander: Writes to the climate entity.
            climate_reader: Reads the climate's requested state and waits for its changes.
            record_store: Keeps the one preheat record of this instance.
            policy: The pure rules for applying and restoring.
            now: Current time, timezone-aware.
            effect_timeout_seconds: Longest wait for the climate to take a command.
        """
        self._commander = commander
        self._reader = climate_reader
        self._store = record_store
        self._policy = policy
        self._now = now
        self._effect_timeout = effect_timeout_seconds
        self._lock = asyncio.Lock()

    async def start(self, timeslot: ScheduledTimeslot) -> ActuationResult:
        """Apply the slot's action to the climate, recording the previous state first.

        Args:
            timeslot: The slot to preheat for; without an action it is unsupported.

        Returns:
            ``APPLIED`` once the climate holds the action, ``NOT_APPLIED`` when it does not
            take it, ``SKIPPED`` when a guard stops it, ``UNSUPPORTED`` for a slot with no action.
        """
        action = timeslot.action
        if action is None:
            return ActuationResult.UNSUPPORTED
        async with self._lock:
            snapshot = self._reader.read_climate_snapshot()
            if snapshot is None:
                _LOGGER.debug("Climate unavailable, preheat of %s skipped", timeslot.timeslot_id)
                return ActuationResult.SKIPPED
            decision = self._policy.decide_apply(snapshot, action)
            if decision is not ApplyDecision.APPLY:
                _LOGGER.debug("Preheat of %s not applied: %s", timeslot.timeslot_id, decision.value)
                return _APPLY_DECISION_TO_RESULT[decision]
            await self._record_once(timeslot, snapshot, action)
            await self._commander.apply(action)
            return await self._confirm(action)

    async def cancel(self, timeslot: ScheduledTimeslot, reason: CancelReason) -> None:
        """Undo the preheat of a slot where that is safe, and forget it.

        Args:
            timeslot: The slot whose preheat is cancelled; a record for another slot is kept.
            reason: Why it is cancelled.
        """
        async with self._lock:
            record = await self._store.load()
            if record is None or record.timeslot_id != timeslot.timeslot_id:
                _LOGGER.debug("No preheat record for %s to cancel", timeslot.timeslot_id)
                return
            _LOGGER.debug("Cancelling preheat of %s (%s)", timeslot.timeslot_id, reason.value)
            await self._release(record)

    async def recover(self, next_timeslot: ScheduledTimeslot | None) -> bool:
        """Reconcile a record persisted before a restart or reload.

        Args:
            next_timeslot: The slot that is next now, if any.

        Returns:
            True when the record belongs to ``next_timeslot`` and its slot is still ahead:
            the preheat resumes, with no new record and no command.
        """
        async with self._lock:
            record = await self._store.load()
            if record is None:
                return False
            if self._is_resumable(record, next_timeslot):
                return True
            await self._release(record)
            return False

    def _is_resumable(self, record: PreheatRecord, next_timeslot: ScheduledTimeslot | None) -> bool:
        return (
            next_timeslot is not None
            and record.timeslot_id == next_timeslot.timeslot_id
            and record.slot_time > self._now()
        )

    async def _record_once(
        self, timeslot: ScheduledTimeslot, snapshot: ClimateSnapshot, action: SlotAction
    ) -> None:
        """Save the previous state, unless this slot already has its record."""
        existing = await self._store.load()
        if existing is not None and existing.timeslot_id == timeslot.timeslot_id:
            return
        await self._store.save(
            PreheatRecord(
                timeslot_id=timeslot.timeslot_id,
                scheduler_entity=timeslot.scheduler_entity,
                slot_time=timeslot.target_time,
                previous=self._true_original(existing, snapshot),
                applied=action,
                recorded_at=self._now(),
            )
        )

    def _true_original(
        self, existing: PreheatRecord | None, snapshot: ClimateSnapshot
    ) -> ClimateSnapshot:
        """Return the state to go back to when a record for an earlier slot is being replaced.

        While the climate is still as IHP left it for the earlier slot, the true original is
        that record's previous state; once somebody else changed it, it is the current one.
        """
        if existing is not None and not self._policy.is_claimed_by_other(existing, snapshot):
            return existing.previous
        return snapshot

    async def _confirm(self, action: SlotAction) -> ActuationResult:
        """Wait, up to the timeout, for the climate to hold the action."""
        deadline = monotonic() + self._effect_timeout
        while True:
            snapshot = self._reader.read_climate_snapshot()
            if snapshot is not None and snapshot.matches(action):
                return ActuationResult.APPLIED
            remaining = deadline - monotonic()
            if remaining <= 0 or not await self._reader.wait_for_state_change(remaining):
                _LOGGER.debug("Climate did not take %s before the timeout", action)
                return ActuationResult.NOT_APPLIED

    async def _release(self, record: PreheatRecord) -> None:
        """Restore, leave or discard according to the policy, then forget the record."""
        snapshot = self._reader.read_climate_snapshot()
        decision = self._policy.decide_restore(record, snapshot, self._now())
        _LOGGER.debug("Preheat of %s released: %s", record.timeslot_id, decision.value)
        if decision is RestoreDecision.RESTORE:
            await self._commander.restore(self._policy.restore_fields(record))
        await self._store.clear()
