"""DirectPreheatActuator.hand_over: a closer deadline takes the preheat over, nothing restored."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    CancelReason,
    RestoreFields,
    SlotAction,
)
from tests.unit.application.actuators.fakes import SLOT_TIME, make_snapshot, make_timeslot
from tests.unit.application.actuators.test_direct_preheat_actuator import Harness

PLAN = dict(slot_id="switch.plan_slot", scheduler="switch.plan")
ALARM = dict(slot_id="sensor.alarm_2026-11-14", scheduler="sensor.alarm")


def _alarm(action: str = "comfort", minutes_earlier: int = 60):
    return make_timeslot(
        SlotAction(preset=action), slot_time=SLOT_TIME - timedelta(minutes=minutes_earlier), **ALARM
    )


@pytest.mark.asyncio
async def test_a_closer_deadline_takes_over_and_keeps_the_original_state() -> None:
    h = Harness()
    original = h.climate.snapshot
    await h.actuator.start(make_timeslot(**PLAN))  # preheat for the schedule: comfort

    result = await h.actuator.hand_over(_alarm())

    assert result is ActuationResult.APPLIED
    assert h.commander.restored == []
    assert h.store.record is not None
    assert h.store.record.timeslot_id == "sensor.alarm_2026-11-14"
    assert h.store.record.scheduler_entity == "sensor.alarm"
    assert h.store.record.previous == original
    assert h.store.record.slot_time == SLOT_TIME - timedelta(minutes=60)


@pytest.mark.asyncio
async def test_the_new_deadline_can_undo_the_preheat_later() -> None:
    h = Harness()
    await h.actuator.start(make_timeslot(**PLAN))
    slot = _alarm()
    await h.actuator.hand_over(slot)

    await h.actuator.cancel(slot, CancelReason.SLOT_CHANGED)

    assert h.commander.restored == [RestoreFields(preset="eco")]
    assert h.store.record is None


@pytest.mark.asyncio
async def test_a_different_target_is_applied_over_the_preheat() -> None:
    h = Harness()
    await h.actuator.start(make_timeslot(**PLAN))

    await h.actuator.hand_over(_alarm("boost"))

    assert h.commander.applied[-1] == SlotAction(preset="boost")
    assert h.store.record is not None and h.store.record.applied == SlotAction(preset="boost")
    assert h.store.record.previous.preset == "eco"


@pytest.mark.asyncio
async def test_the_same_target_sends_no_new_command() -> None:
    h = Harness()
    await h.actuator.start(make_timeslot(**PLAN))
    sent = len(h.commander.applied)

    await h.actuator.hand_over(_alarm("comfort"))

    assert len(h.commander.applied) == sent


@pytest.mark.asyncio
async def test_somebody_elses_change_is_respected_by_the_new_deadline() -> None:
    h = Harness()
    await h.actuator.start(make_timeslot(**PLAN))
    h.climate.snapshot = make_snapshot(preset="boost")  # changed by the user meanwhile
    sent = len(h.commander.applied)

    result = await h.actuator.hand_over(_alarm("comfort"))

    assert result is ActuationResult.SKIPPED
    assert len(h.commander.applied) == sent
    assert h.store.record is not None and h.store.record.claimed


@pytest.mark.asyncio
async def test_a_claim_survives_the_hand_over_and_a_snooze_after_it() -> None:
    h = Harness()
    await h.actuator.start(make_timeslot(**PLAN))
    h.climate.snapshot = make_snapshot(preset="boost")
    await h.actuator.hand_over(_alarm("comfort"))
    sent = len(h.commander.applied)

    result = await h.actuator.start(_alarm("comfort", minutes_earlier=45))  # a snooze

    assert result is ActuationResult.SKIPPED
    assert len(h.commander.applied) == sent


@pytest.mark.asyncio
async def test_without_a_preheat_in_progress_a_hand_over_is_a_plain_start() -> None:
    h = Harness()

    result = await h.actuator.hand_over(_alarm())

    assert result is ActuationResult.APPLIED
    assert h.store.record is not None and h.store.record.previous.preset == "eco"


@pytest.mark.asyncio
async def test_a_slot_without_an_action_is_unsupported() -> None:
    h = Harness()
    slot = make_timeslot(**PLAN)
    bare = type(slot)(
        target_time=slot.target_time,
        target_temp=slot.target_temp,
        timeslot_id=slot.timeslot_id,
        scheduler_entity=slot.scheduler_entity,
    )

    assert await h.actuator.hand_over(bare) is ActuationResult.UNSUPPORTED


@pytest.mark.asyncio
async def test_a_snooze_does_not_apply_the_target_again_over_a_manual_change() -> None:
    h = Harness()
    await h.actuator.start(_alarm())
    h.climate.snapshot = make_snapshot(preset="boost")  # the user took over
    sent = len(h.commander.applied)

    result = await h.actuator.hand_over(_alarm(minutes_earlier=45))

    assert result is ActuationResult.SKIPPED
    assert len(h.commander.applied) == sent
    assert h.store.record is not None and h.store.record.claimed
    assert h.store.record.slot_time == SLOT_TIME - timedelta(minutes=45)
