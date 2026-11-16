"""ScheduleAnticipationActionUseCase: the hold of a wake-up slot, its timer and its early end."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import ISchedulerReader
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
    SlotAction,
)

NOW = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)
HOLD = timedelta(minutes=90)
ALARM = "sensor.phone_next_alarm"


def _slot(hold: timedelta | None = HOLD) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=NOW,
        target_temp=21.0,
        timeslot_id=f"{ALARM}_2026-11-16",
        scheduler_entity=ALARM,
        action=SlotAction(preset="comfort"),
        hold=hold,
    )


def _scheduler_slot(at: datetime) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=at, target_temp=21.0, timeslot_id="plan_slot", scheduler_entity="switch.plan"
    )


def _build(next_scheduler: ScheduledTimeslot | None = None):
    control = Mock()
    control.is_preheating_active = Mock(return_value=True)
    control.get_preheating_target_time = Mock(return_value=NOW)
    control.get_active_timeslot = Mock(return_value=_slot())
    control.mark_preheating_complete = AsyncMock()
    control.end_hold = AsyncMock()
    control.cancel_preheating = AsyncMock()
    control.get_active_scheduler_entity = Mock(return_value=ALARM)
    reader = Mock(spec=ISchedulerReader)
    reader.get_next_scheduler_timeslot = AsyncMock(return_value=next_scheduler)
    timer = Mock()
    cancels: list[Mock] = []
    callbacks: list[tuple[datetime, object]] = []

    def schedule(when, callback):
        cancel = Mock()
        cancels.append(cancel)
        callbacks.append((when, callback))
        return cancel

    timer.schedule_timer = Mock(side_effect=schedule)
    use_case = ScheduleAnticipationActionUseCase(reader, timer, control)
    return use_case, control, callbacks, cancels


async def _reach_deadline(use_case) -> None:
    with patch("homeassistant.util.dt.now", return_value=NOW + timedelta(seconds=5)):
        await use_case._complete_elapsed_preheating()


@pytest.mark.asyncio
async def test_a_slot_with_a_hold_completes_into_the_hold_and_arms_its_timer() -> None:
    use_case, control, callbacks, _ = _build()

    await _reach_deadline(use_case)

    control.mark_preheating_complete.assert_awaited_once_with(NOW + HOLD, False)
    assert [when for when, _ in callbacks] == [NOW + HOLD]


@pytest.mark.asyncio
async def test_the_hold_timer_ends_the_hold() -> None:
    use_case, control, callbacks, _ = _build()
    await _reach_deadline(use_case)

    await callbacks[0][1]()

    control.end_hold.assert_awaited_once()
    assert control.end_hold.await_args.args[0].timeslot_id == f"{ALARM}_2026-11-16"


@pytest.mark.asyncio
async def test_a_scheduler_slot_before_the_end_bounds_the_hold_as_a_handoff() -> None:
    scheduler = _scheduler_slot(NOW + timedelta(minutes=30))
    use_case, control, callbacks, _ = _build(next_scheduler=scheduler)

    await _reach_deadline(use_case)

    control.mark_preheating_complete.assert_awaited_once_with(NOW + timedelta(minutes=30), True)
    assert [when for when, _ in callbacks] == [NOW + timedelta(minutes=30)]


@pytest.mark.asyncio
async def test_a_scheduler_slot_after_the_end_does_not_bound_the_hold() -> None:
    use_case, control, _, _ = _build(next_scheduler=_scheduler_slot(NOW + timedelta(hours=5)))

    await _reach_deadline(use_case)

    control.mark_preheating_complete.assert_awaited_once_with(NOW + HOLD, False)


@pytest.mark.asyncio
async def test_a_scheduler_slot_at_the_deadline_ends_the_hold_at_once() -> None:
    use_case, control, callbacks, _ = _build(next_scheduler=_scheduler_slot(NOW))

    await _reach_deadline(use_case)

    control.mark_preheating_complete.assert_awaited_once_with(NOW, True)
    control.end_hold.assert_awaited_once()
    assert callbacks == []


@pytest.mark.asyncio
async def test_without_a_hold_the_slot_completes_as_before() -> None:
    use_case, control, callbacks, _ = _build()
    control.get_active_timeslot = Mock(return_value=_slot(hold=None))

    await _reach_deadline(use_case)

    control.mark_preheating_complete.assert_awaited_once_with()
    assert callbacks == []


@pytest.mark.asyncio
async def test_disabling_ihp_during_a_hold_ends_it_as_a_cancellation() -> None:
    use_case, control, _, cancels = _build()
    await _reach_deadline(use_case)

    await use_case.end_pending_hold()

    control.end_hold.assert_awaited_once()
    cancels[0].assert_called_once()
    # a second call has nothing left to end
    await use_case.end_pending_hold()
    control.end_hold.assert_awaited_once()


@pytest.mark.asyncio
async def test_unloading_drops_the_hold_timer_but_not_the_record() -> None:
    use_case, control, _, cancels = _build()
    await _reach_deadline(use_case)

    use_case.cancel_pending_timers()

    cancels[0].assert_called_once()
    control.end_hold.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_hold_found_after_a_restart_gets_its_timer_back() -> None:
    use_case, control, callbacks, _ = _build()
    registered = control.set_on_hold_recovered.call_args.args[0]

    with patch("homeassistant.util.dt.now", return_value=NOW + timedelta(minutes=10)):
        await registered(_slot(), NOW + HOLD)

    assert [when for when, _ in callbacks] == [NOW + HOLD]


@pytest.mark.asyncio
async def test_a_new_hold_replaces_the_timer_of_the_previous_one() -> None:
    use_case, _, callbacks, cancels = _build()
    await _reach_deadline(use_case)

    with patch("homeassistant.util.dt.now", return_value=NOW + timedelta(minutes=10)):
        await use_case._arm_hold_timer(_slot(), NOW + timedelta(hours=3))

    cancels[0].assert_called_once()
    assert len(callbacks) == 2


def _control_with_active_source(active: bool = True):
    use_case, control, callbacks, cancels = _build()
    control.is_preheating_active = Mock(return_value=active)
    use_case._scheduler_reader.is_wake_up_source = Mock(side_effect=lambda e: e == ALARM)
    use_case._on_deadline = AsyncMock()
    return use_case, control, callbacks, cancels


def test_a_deadline_timer_is_armed_for_an_active_wake_up_preheat() -> None:
    use_case, _, callbacks, _ = _control_with_active_source()

    use_case._ensure_deadline_timer()
    use_case._ensure_deadline_timer()  # idempotent

    assert [when for when, _ in callbacks] == [NOW + timedelta(seconds=1)]


@pytest.mark.asyncio
async def test_the_deadline_timer_asks_for_a_recalculation() -> None:
    use_case, _, callbacks, _ = _control_with_active_source()
    use_case._ensure_deadline_timer()

    await callbacks[0][1]()

    use_case._on_deadline.assert_awaited_once()


def test_no_deadline_timer_without_an_active_preheat_or_for_a_scheduler() -> None:
    use_case, control, callbacks, _ = _control_with_active_source(active=False)
    use_case._ensure_deadline_timer()
    assert callbacks == []

    control.is_preheating_active = Mock(return_value=True)
    use_case._scheduler_reader.is_wake_up_source = Mock(return_value=False)
    use_case._ensure_deadline_timer()
    assert callbacks == []


def test_the_deadline_timer_is_replaced_when_the_deadline_moves() -> None:
    use_case, control, callbacks, cancels = _control_with_active_source()
    use_case._ensure_deadline_timer()

    control.get_preheating_target_time = Mock(return_value=NOW + timedelta(minutes=10))
    use_case._ensure_deadline_timer()

    cancels[0].assert_called_once()
    assert len(callbacks) == 2
