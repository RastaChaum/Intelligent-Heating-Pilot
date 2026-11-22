"""Unit tests for DirectPreheatActuator, over fake ports."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from custom_components.intelligent_heating_pilot.application.actuators.direct_preheat_actuator import (
    DirectPreheatActuator,
)
from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    CancelReason,
    PreheatRecord,
    RecoveryOutcome,
    RestoreFields,
    SlotAction,
)
from tests.unit.application.actuators.fakes import (
    NOW,
    SLOT_TIME,
    FakeClimate,
    FakeCommander,
    FakeStore,
    make_snapshot,
    make_timeslot,
)


class Harness:
    def __init__(self, timeout: float = 0.05) -> None:
        self.events: list[str] = []
        self.climate = FakeClimate()
        self.commander = FakeCommander(self.climate, self.events)
        self.store = FakeStore(self.events)
        self.now = NOW
        self.actuator = DirectPreheatActuator(
            commander=self.commander,
            climate_reader=self.climate,  # type: ignore[arg-type]
            record_store=self.store,
            policy=PreheatSessionPolicy(),
            now=lambda: self.now,
            effect_timeout_seconds=timeout,
        )


@pytest.fixture
def h() -> Harness:
    return Harness()


class TestStart:
    @pytest.mark.asyncio
    async def test_the_slot_action_is_applied_and_confirmed(self, h: Harness) -> None:
        result = await h.actuator.start(make_timeslot())

        assert result is ActuationResult.APPLIED
        assert h.commander.applied == [SlotAction(preset="comfort")]

    @pytest.mark.asyncio
    async def test_the_previous_state_is_recorded_before_the_first_write(self, h: Harness) -> None:
        await h.actuator.start(make_timeslot())

        assert h.events[:2] == ["save", "apply"]
        assert h.store.record is not None
        assert h.store.record.previous == make_snapshot()
        assert h.store.record.applied == SlotAction(preset="comfort")

    @pytest.mark.asyncio
    async def test_a_second_start_for_the_same_slot_changes_nothing(self, h: Harness) -> None:
        await h.actuator.start(make_timeslot())
        result = await h.actuator.start(make_timeslot())

        assert result is ActuationResult.APPLIED
        assert len(h.commander.applied) == 1
        assert h.store.saves == 1

    @pytest.mark.asyncio
    async def test_two_starts_at_once_record_and_apply_once(self, h: Harness) -> None:
        results = await asyncio.gather(
            h.actuator.start(make_timeslot()), h.actuator.start(make_timeslot())
        )

        assert results == [ActuationResult.APPLIED, ActuationResult.APPLIED]
        assert len(h.commander.applied) == 1
        assert h.store.saves == 1

    @pytest.mark.asyncio
    async def test_a_retry_keeps_the_original_previous_state(self, h: Harness) -> None:
        h.climate.ignore_commands = True
        first = await h.actuator.start(make_timeslot())
        h.climate.ignore_commands = False
        second = await h.actuator.start(make_timeslot())

        assert first is ActuationResult.NOT_APPLIED
        assert second is ActuationResult.APPLIED
        assert h.store.saves == 1
        assert h.store.record is not None and h.store.record.previous == make_snapshot()

    @pytest.mark.asyncio
    async def test_a_climate_that_is_off_is_skipped_without_a_command_or_a_record(
        self, h: Harness
    ) -> None:
        h.climate.snapshot = make_snapshot(hvac_mode="off")

        result = await h.actuator.start(make_timeslot())

        assert result is ActuationResult.SKIPPED
        assert h.commander.applied == []
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_preset_the_climate_does_not_offer_is_not_applied(self, h: Harness) -> None:
        result = await h.actuator.start(make_timeslot(SlotAction(preset="away")))

        assert result is ActuationResult.NOT_APPLIED
        assert h.commander.applied == []
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_an_action_already_in_place_needs_no_command_and_no_record(
        self, h: Harness
    ) -> None:
        h.climate.snapshot = make_snapshot(preset="comfort")

        result = await h.actuator.start(make_timeslot())

        assert result is ActuationResult.APPLIED
        assert h.commander.applied == [] and h.store.record is None

    @pytest.mark.asyncio
    async def test_a_slot_without_an_action_is_unsupported(self, h: Harness) -> None:
        slot = make_timeslot()
        slot = type(slot)(
            slot.target_time, slot.target_temp, slot.timeslot_id, slot.scheduler_entity
        )

        assert await h.actuator.start(slot) is ActuationResult.UNSUPPORTED
        assert h.commander.applied == []

    @pytest.mark.asyncio
    async def test_an_unavailable_climate_is_skipped(self, h: Harness) -> None:
        h.climate.snapshot = None

        assert await h.actuator.start(make_timeslot()) is ActuationResult.SKIPPED

    @pytest.mark.asyncio
    async def test_the_effect_is_awaited_when_the_climate_applies_late(self, h: Harness) -> None:
        h.climate.apply_on_next_wait = True

        result = await h.actuator.start(make_timeslot())

        assert result is ActuationResult.APPLIED
        assert h.climate.waits >= 1

    @pytest.mark.asyncio
    async def test_a_command_without_effect_is_not_applied_after_the_timeout(
        self, h: Harness
    ) -> None:
        h.climate.ignore_commands = True

        assert await h.actuator.start(make_timeslot()) is ActuationResult.NOT_APPLIED

    @pytest.mark.asyncio
    async def test_a_temperature_slot_is_confirmed_on_the_temperature(self, h: Harness) -> None:
        result = await h.actuator.start(make_timeslot(SlotAction(temperature=21.0)))

        assert result is ActuationResult.APPLIED
        assert h.commander.applied == [SlotAction(temperature=21.0)]

    @pytest.mark.asyncio
    async def test_a_later_slot_keeps_the_true_original_while_the_earlier_one_is_still_ours(
        self, h: Harness
    ) -> None:
        await h.actuator.start(make_timeslot(slot_id="slot_a"))
        h.climate.snapshot = make_snapshot(preset="comfort")  # still ours
        await h.actuator.start(make_timeslot(SlotAction(preset="boost"), slot_id="slot_b"))

        assert h.store.record is not None
        assert h.store.record.timeslot_id == "slot_b"
        assert h.store.record.previous == make_snapshot()  # eco, the state before slot_a

    @pytest.mark.asyncio
    async def test_a_later_slot_records_the_current_state_when_someone_else_took_over(
        self, h: Harness
    ) -> None:
        await h.actuator.start(make_timeslot(slot_id="slot_a"))
        h.climate.snapshot = make_snapshot(preset="boost")  # changed by someone else
        await h.actuator.start(make_timeslot(SlotAction(preset="comfort"), slot_id="slot_b"))

        assert h.store.record is not None
        assert h.store.record.previous.preset == "boost"


class TestCancel:
    async def _started(self, h: Harness, **kwargs):
        slot = make_timeslot(**kwargs)
        await h.actuator.start(slot)
        h.events.clear()
        return slot

    @pytest.mark.asyncio
    async def test_an_untouched_climate_is_restored_and_the_record_cleared(
        self, h: Harness
    ) -> None:
        slot = await self._started(h)

        await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

        assert h.commander.restored == [RestoreFields(preset="eco")]
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_change_by_another_party_is_never_overwritten(self, h: Harness) -> None:
        slot = await self._started(h)
        h.climate.snapshot = make_snapshot(preset="boost")

        await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

        assert h.commander.restored == []
        # Kept, marked as taken over: IHP must not apply this slot again over that change
        assert h.store.record is not None and h.store.record.claimed

    @pytest.mark.asyncio
    async def test_a_cancellation_inside_the_guard_window_restores_nothing(
        self, h: Harness
    ) -> None:
        slot = await self._started(h)
        h.now = SLOT_TIME - timedelta(minutes=2)

        await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

        assert h.commander.restored == []
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_reaching_the_slot_discards_the_record_without_restoring(
        self, h: Harness
    ) -> None:
        slot = await self._started(h)
        h.now = SLOT_TIME

        await h.actuator.cancel(slot, CancelReason.SLOT_REACHED)

        assert h.commander.restored == []
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_cancellation_for_another_slot_is_ignored(self, h: Harness) -> None:
        await self._started(h)

        await h.actuator.cancel(make_timeslot(slot_id="other"), CancelReason.SLOT_CHANGED)

        assert h.commander.restored == []
        assert h.store.record is not None

    @pytest.mark.asyncio
    async def test_a_cancellation_without_a_record_does_nothing(self, h: Harness) -> None:
        await h.actuator.cancel(make_timeslot(), CancelReason.IHP_DISABLED)

        assert h.events == []

    @pytest.mark.asyncio
    async def test_the_hvac_mode_is_never_restored(self, h: Harness) -> None:
        slot = await self._started(h)

        await h.actuator.cancel(slot, CancelReason.IHP_DISABLED)

        assert all(not hasattr(fields, "hvac_mode") for fields in h.commander.restored)


def _own_next(slot=None, calls=None):
    """Build a next_timeslot_of that answers for the slot's scheduler (None: cannot answer)."""

    async def next_timeslot_of(entity_id: str):
        if calls is not None:
            calls.append(entity_id)
        return slot

    return next_timeslot_of


class TestRecover:
    def _record(self, **overrides) -> PreheatRecord:
        values = {
            "timeslot_id": "switch.plan_slot",
            "scheduler_entity": "switch.plan",
            "slot_time": SLOT_TIME,
            "previous": make_snapshot(),
            "applied": SlotAction(preset="comfort"),
            "recorded_at": NOW,
        }
        values.update(overrides)
        return PreheatRecord(**values)

    @pytest.mark.asyncio
    async def test_without_a_record_there_is_nothing_to_recover(self, h: Harness) -> None:
        recovery = await h.actuator.recover(_own_next(make_timeslot()))

        assert recovery.outcome is RecoveryOutcome.NOTHING

    @pytest.mark.asyncio
    async def test_a_record_for_the_slot_its_scheduler_still_has_resumes(self, h: Harness) -> None:
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        recovery = await h.actuator.recover(_own_next(make_timeslot()))

        assert recovery.outcome is RecoveryOutcome.RESUMED
        assert recovery.timeslot == make_timeslot()
        assert h.store.saves == 0 and h.commander.restored == []

    @pytest.mark.asyncio
    async def test_the_scheduler_of_the_record_is_the_one_asked(self, h: Harness) -> None:
        """Another scheduler may be next: only the record's own scheduler tells if its slot stands."""
        h.store.record = self._record()
        asked: list[str] = []

        await h.actuator.recover(_own_next(make_timeslot(), asked))

        assert asked == ["switch.plan"]

    @pytest.mark.asyncio
    async def test_a_record_for_another_slot_of_its_scheduler_is_restored(self, h: Harness) -> None:
        h.store.record = self._record(timeslot_id="old_slot")
        h.climate.snapshot = make_snapshot(preset="comfort")

        recovery = await h.actuator.recover(_own_next(make_timeslot(slot_id="new_slot")))

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == [RestoreFields(preset="eco")]
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_scheduler_that_cannot_answer_defers_and_keeps_the_record(
        self, h: Harness
    ) -> None:
        """No restore on a missing answer: the preheat may still be valid (a read error is not a removal)."""
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        recovery = await h.actuator.recover(_own_next(None))

        assert recovery.outcome is RecoveryOutcome.DEFERRED
        assert h.commander.restored == []
        assert h.store.record is not None

    @pytest.mark.asyncio
    async def test_a_record_for_a_slot_already_reached_is_discarded_without_asking(
        self, h: Harness
    ) -> None:
        h.store.record = self._record()
        h.now = SLOT_TIME + timedelta(minutes=30)
        h.climate.snapshot = make_snapshot(preset="comfort")
        asked: list[str] = []

        recovery = await h.actuator.recover(_own_next(None, asked))

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == [] and h.store.record is None
        assert asked == []

    @pytest.mark.asyncio
    async def test_a_claimed_record_resumes_nothing_but_stays(self, h: Harness) -> None:
        h.store.record = self._record(claimed=True)

        recovery = await h.actuator.recover(_own_next(make_timeslot()))

        assert recovery.outcome is RecoveryOutcome.NOTHING
        assert h.store.record is not None and h.store.record.claimed

    @pytest.mark.asyncio
    async def test_recover_is_idempotent(self, h: Harness) -> None:
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        first = await h.actuator.recover(_own_next(make_timeslot()))
        second = await h.actuator.recover(_own_next(make_timeslot()))

        assert first.outcome is second.outcome is RecoveryOutcome.RESUMED
        assert h.store.saves == 0


class TestTakeover:
    """A change by someone else is final for the slot: IHP never applies the slot over it (M1)."""

    @pytest.mark.asyncio
    async def test_after_a_manual_change_a_later_start_for_the_same_slot_writes_nothing(
        self, h: Harness
    ) -> None:
        slot = make_timeslot()
        await h.actuator.start(slot)
        h.climate.snapshot = make_snapshot(preset="none", temperature=19.0)  # the user's choice
        await h.actuator.cancel(slot, CancelReason.POSTPONED)  # IHP's anticipation moved
        h.commander.applied.clear()

        result = await h.actuator.start(slot)  # the timer fires again

        assert result is ActuationResult.SKIPPED
        assert h.commander.applied == []
        assert h.climate.snapshot is not None and h.climate.snapshot.temperature == 19.0

    @pytest.mark.asyncio
    async def test_the_takeover_is_kept_across_a_restart(self, h: Harness) -> None:
        slot = make_timeslot()
        await h.actuator.start(slot)
        h.climate.snapshot = make_snapshot(preset="boost")
        await h.actuator.cancel(slot, CancelReason.POSTPONED)

        assert h.store.record is not None and h.store.record.claimed

    @pytest.mark.asyncio
    async def test_a_takeover_does_not_block_the_next_slot(self, h: Harness) -> None:
        await h.actuator.start(make_timeslot(slot_id="slot_a"))
        h.climate.snapshot = make_snapshot(preset="boost")
        await h.actuator.cancel(make_timeslot(slot_id="slot_a"), CancelReason.POSTPONED)
        h.climate.snapshot = make_snapshot(preset="eco")

        result = await h.actuator.start(make_timeslot(slot_id="slot_b"))

        assert result is ActuationResult.APPLIED

    @pytest.mark.asyncio
    async def test_reaching_the_slot_clears_a_takeover(self, h: Harness) -> None:
        slot = make_timeslot()
        await h.actuator.start(slot)
        h.climate.snapshot = make_snapshot(preset="boost")
        await h.actuator.cancel(slot, CancelReason.POSTPONED)
        h.now = SLOT_TIME

        await h.actuator.cancel(slot, CancelReason.SLOT_REACHED)

        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_an_unavailable_climate_keeps_the_record_untouched(self, h: Harness) -> None:
        slot = make_timeslot()
        await h.actuator.start(slot)
        h.climate.snapshot = None

        await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

        assert h.store.record is not None and not h.store.record.claimed
        assert h.commander.restored == []

    @pytest.mark.asyncio
    async def test_a_switched_off_climate_is_left_alone_and_claimed(self, h: Harness) -> None:
        slot = make_timeslot()
        await h.actuator.start(slot)
        h.climate.snapshot = make_snapshot(hvac_mode="off", preset="comfort")

        await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

        assert h.commander.restored == []
        assert h.store.record is not None and h.store.record.claimed


class TestChaining:
    @pytest.mark.asyncio
    async def test_a_slot_already_passed_is_not_chained_to_the_next_one(self, h: Harness) -> None:
        """M4: slot A was applied by its scheduler; going back to the state before A would undo it."""
        await h.actuator.start(make_timeslot(slot_id="slot_a"))
        h.now = SLOT_TIME + timedelta(hours=1)  # slot A passed and its record survived
        h.climate.snapshot = make_snapshot(
            preset="comfort"
        )  # still A's action, applied by the scheduler

        await h.actuator.start(
            make_timeslot(
                SlotAction(preset="boost"),
                slot_id="slot_b",
                slot_time=SLOT_TIME + timedelta(hours=5),
            )
        )

        assert h.store.record is not None
        assert h.store.record.previous.preset == "comfort"
