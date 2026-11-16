"""A wake-up deadline that moves keeps its identity: the record follows it, ownership stays."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    SlotAction,
)
from tests.unit.application.actuators.fakes import SLOT_TIME, make_snapshot, make_timeslot
from tests.unit.application.actuators.test_direct_preheat_actuator import Harness

SLOT_ID = "sensor.phone_next_alarm_2026-11-14"


def _alarm(minutes_late: int = 0):
    return make_timeslot(
        slot_id=SLOT_ID,
        slot_time=SLOT_TIME + timedelta(minutes=minutes_late),
        scheduler="sensor.phone_next_alarm",
    )


@pytest.mark.asyncio
async def test_a_snooze_refreshes_the_slot_time_of_the_record_and_keeps_the_original_state() -> (
    None
):
    h = Harness()
    original = h.climate.snapshot
    await h.actuator.start(_alarm())

    await h.actuator.start(_alarm(minutes_late=10))

    assert h.store.record is not None
    assert h.store.record.slot_time == SLOT_TIME + timedelta(minutes=10)
    assert h.store.record.previous == original


@pytest.mark.asyncio
async def test_a_snooze_after_a_manual_change_does_not_apply_the_target_again() -> None:
    h = Harness()
    await h.actuator.start(_alarm())
    # The user takes the thermostat over: the record is claimed by the next cancellation
    h.climate.snapshot = make_snapshot(preset="boost")
    await h.actuator.cancel(_alarm(), _reason())
    applied_before = len(h.commander.applied)

    result = await h.actuator.start(_alarm(minutes_late=10))

    assert result is ActuationResult.SKIPPED
    assert len(h.commander.applied) == applied_before


def _reason():
    from custom_components.intelligent_heating_pilot.domain.value_objects import CancelReason

    return CancelReason.SLOT_CHANGED


@pytest.mark.asyncio
async def test_the_same_start_twice_writes_the_record_once() -> None:
    h = Harness()
    await h.actuator.start(_alarm())
    saves = h.store.saves

    await h.actuator.start(_alarm())

    assert h.store.saves == saves
    assert h.commander.applied == [SlotAction(preset="comfort")]


@pytest.mark.asyncio
async def test_a_claim_follows_a_snoozed_deadline() -> None:
    """A claim lasts until the slot: a snooze past the old time must not end it early."""
    h = Harness()
    await h.actuator.start(_alarm())
    h.climate.snapshot = make_snapshot(preset="boost")
    await h.actuator.cancel(_alarm(), _reason())  # claimed, kept until the slot
    h.now = SLOT_TIME + timedelta(minutes=5)  # past the old time, before the snoozed one

    result = await h.actuator.start(_alarm(minutes_late=30))

    assert result is ActuationResult.SKIPPED
    assert h.store.record is not None
    assert h.store.record.slot_time == SLOT_TIME + timedelta(minutes=30)
