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
        assert h.store.record is None

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
    async def test_without_a_record_nothing_is_in_progress(self, h: Harness) -> None:
        assert await h.actuator.recover(make_timeslot()) is False

    @pytest.mark.asyncio
    async def test_a_record_for_the_next_slot_resumes_without_recording_again(
        self, h: Harness
    ) -> None:
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        assert await h.actuator.recover(make_timeslot()) is True
        assert h.store.saves == 0 and h.commander.restored == []

    @pytest.mark.asyncio
    async def test_a_record_for_another_slot_is_reconciled_and_restored(self, h: Harness) -> None:
        h.store.record = self._record(timeslot_id="old_slot")
        h.climate.snapshot = make_snapshot(preset="comfort")

        assert await h.actuator.recover(make_timeslot(slot_id="new_slot")) is False
        assert h.commander.restored == [RestoreFields(preset="eco")]
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_record_for_a_slot_already_reached_is_discarded(self, h: Harness) -> None:
        h.store.record = self._record()
        h.now = SLOT_TIME + timedelta(minutes=30)
        h.climate.snapshot = make_snapshot(preset="comfort")

        assert await h.actuator.recover(None) is False
        assert h.commander.restored == []
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_record_with_nobody_next_is_restored_when_still_ours(self, h: Harness) -> None:
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        assert await h.actuator.recover(None) is False
        assert h.commander.restored == [RestoreFields(preset="eco")]

    @pytest.mark.asyncio
    async def test_recover_is_idempotent(self, h: Harness) -> None:
        h.store.record = self._record()
        h.climate.snapshot = make_snapshot(preset="comfort")

        first = await h.actuator.recover(make_timeslot())
        second = await h.actuator.recover(make_timeslot())

        assert first is second is True
        assert h.store.saves == 0
