"""Hold after a wake-up deadline: begin, end, survive a restart, release what is orphaned."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.intelligent_heating_pilot.application.actuators.direct_preheat_actuator import (
    DirectPreheatActuator,
)
from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CancelReason,
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

ALARM = "sensor.phone_next_alarm"
HOLD = timedelta(minutes=90)


def _alarm(hold: timedelta | None = HOLD):
    slot = make_timeslot(slot_id=f"{ALARM}_2026-11-14", scheduler=ALARM)
    return replace(slot, hold=hold)


class Harness:
    def __init__(self, configured: frozenset[str] | None = None) -> None:
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
            effect_timeout_seconds=0.05,
            configured_entities=(lambda: configured) if configured is not None else None,
        )

    async def preheat_until_deadline(self) -> None:
        """Preheat, then let the clock reach the deadline."""
        await self.actuator.start(_alarm())
        self.now = SLOT_TIME


async def _no_next(_entity: str):
    return None


@pytest.mark.asyncio
async def test_a_hold_keeps_the_record_and_its_end_restores_the_earlier_state() -> None:
    h = Harness()
    await h.preheat_until_deadline()

    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    assert h.store.record is not None and h.store.record.hold_until == SLOT_TIME + HOLD

    h.now = SLOT_TIME + HOLD
    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == [RestoreFields(preset="eco")]
    assert h.store.record is None


@pytest.mark.asyncio
async def test_a_change_during_the_hold_is_kept() -> None:
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    h.climate.snapshot = make_snapshot(preset="boost")
    h.now = SLOT_TIME + HOLD

    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == []
    assert h.store.record is None


@pytest.mark.asyncio
async def test_a_scheduler_handoff_ends_the_hold_without_a_restore() -> None:
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + timedelta(minutes=30), handoff=True)
    h.now = SLOT_TIME + timedelta(minutes=30)

    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == []
    assert h.store.record is None


@pytest.mark.asyncio
async def test_ending_a_hold_that_was_never_begun_does_nothing() -> None:
    h = Harness()
    await h.preheat_until_deadline()

    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == []
    assert h.store.record is not None  # still the preheat's record, untouched


@pytest.mark.asyncio
async def test_a_hold_of_another_slot_is_not_ended() -> None:
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    other = replace(_alarm(), timeslot_id=f"{ALARM}_2026-11-15")

    await h.actuator.end_hold(other)
    await h.actuator.begin_hold(other, SLOT_TIME + timedelta(hours=9), handoff=False)

    assert h.store.record is not None
    assert h.store.record.hold_until == SLOT_TIME + HOLD


@pytest.mark.asyncio
async def test_without_a_hold_reaching_the_slot_still_forgets_the_record() -> None:
    h = Harness()
    await h.preheat_until_deadline()

    await h.actuator.cancel(_alarm(hold=None), CancelReason.SLOT_REACHED)

    assert h.store.record is None
    assert h.commander.restored == []


class TestRecovery:
    @pytest.mark.asyncio
    async def test_a_running_hold_is_resumed_after_a_restart(self) -> None:
        h = Harness()
        await h.preheat_until_deadline()
        await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
        h.now = SLOT_TIME + timedelta(minutes=10)

        recovery = await h.actuator.recover(_no_next)

        assert recovery.outcome is RecoveryOutcome.HOLDING
        assert recovery.hold_until == SLOT_TIME + HOLD
        assert recovery.timeslot is not None and recovery.timeslot.timeslot_id.startswith(ALARM)
        assert h.store.record is not None

    @pytest.mark.asyncio
    async def test_a_hold_that_ended_during_the_restart_is_ended_now(self) -> None:
        h = Harness()
        await h.preheat_until_deadline()
        await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
        h.now = SLOT_TIME + HOLD + timedelta(minutes=5)

        recovery = await h.actuator.recover(_no_next)

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == [RestoreFields(preset="eco")]
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_an_expired_handoff_hold_restores_nothing(self) -> None:
        h = Harness()
        await h.preheat_until_deadline()
        await h.actuator.begin_hold(_alarm(), SLOT_TIME + timedelta(minutes=30), handoff=True)
        h.now = SLOT_TIME + timedelta(hours=1)

        recovery = await h.actuator.recover(_no_next)

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == []

    @pytest.mark.asyncio
    async def test_a_source_removed_from_the_options_releases_its_preheat(self) -> None:
        h = Harness(configured=frozenset({"switch.plan"}))
        await h.actuator.start(_alarm())  # still ahead of its deadline

        recovery = await h.actuator.recover(_no_next)

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == [RestoreFields(preset="eco")]
        assert h.store.record is None

    @pytest.mark.asyncio
    async def test_a_source_removed_during_its_hold_restores_unless_claimed(self) -> None:
        h = Harness(configured=frozenset({"switch.plan"}))
        await h.preheat_until_deadline()
        await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
        h.now = SLOT_TIME + timedelta(minutes=10)

        recovery = await h.actuator.recover(_no_next)

        assert recovery.outcome is RecoveryOutcome.RELEASED
        assert h.commander.restored == [RestoreFields(preset="eco")]

    @pytest.mark.asyncio
    async def test_a_configured_source_is_not_released(self) -> None:
        h = Harness(configured=frozenset({ALARM}))
        await h.actuator.start(_alarm())

        async def own_next(_entity: str):
            return _alarm()

        recovery = await h.actuator.recover(own_next)

        assert recovery.outcome is RecoveryOutcome.RESUMED


@pytest.mark.asyncio
async def test_a_new_preheat_during_a_hold_keeps_the_true_original_state() -> None:
    """While the hold runs and nobody touched the setting, the earlier state is still the original."""
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    h.now = SLOT_TIME + timedelta(minutes=30)
    tomorrow = make_timeslot(
        action=SlotAction(preset="boost"),
        slot_id="switch.plan_tomorrow",
        slot_time=SLOT_TIME + timedelta(hours=20),
    )

    await h.actuator.start(tomorrow)

    assert h.store.record is not None
    assert h.store.record.previous.preset == "eco"


@pytest.mark.asyncio
async def test_a_second_alarm_on_the_same_date_ends_the_old_hold_and_its_timer_changes_nothing() -> (
    None
):
    """The sensor moves from 05:30 (hold until 07:00) to 07:30 the same day: the old timer must not
    restore in the middle of the new preheat."""
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    h.now = SLOT_TIME + timedelta(minutes=20)
    later = replace(_alarm(), target_time=SLOT_TIME + timedelta(hours=2))

    await h.actuator.start(later)  # same id, a later time: the hold belonged to the earlier time

    assert h.store.record is not None and h.store.record.hold_until is None
    h.now = SLOT_TIME + HOLD  # the old hold timer fires
    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == []
    assert h.store.record is not None


@pytest.mark.asyncio
async def test_a_timer_that_fires_before_the_recorded_end_changes_nothing() -> None:
    h = Harness()
    await h.preheat_until_deadline()
    await h.actuator.begin_hold(_alarm(), SLOT_TIME + HOLD, handoff=False)
    h.now = SLOT_TIME + timedelta(minutes=30)

    await h.actuator.end_hold(_alarm())

    assert h.commander.restored == []
    assert h.store.record is not None
