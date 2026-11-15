"""ScheduleAnticipationActionUseCase: when a wake-up deadline hands the preheat over, and when it reverts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import ISchedulerReader
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
    SlotAction,
)

NOW = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)
ALARM = "sensor.phone_next_alarm"
PLAN = "switch.plan"
TOLERANCE_MINUTES = 15


def _slot(entity: str, at: datetime) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=at,
        target_temp=21.0,
        timeslot_id=f"{entity}_{at.date()}",
        scheduler_entity=entity,
        action=SlotAction(preset="comfort"),
    )


def _build(active_entity: str, preheating_for: datetime, own_next: ScheduledTimeslot | None):
    control = Mock()
    control.is_preheating_active = Mock(return_value=True)
    control.get_preheating_target_time = Mock(return_value=preheating_for)
    control.get_active_scheduler_entity = Mock(return_value=active_entity)
    control.cancel_preheating = AsyncMock()
    control.hand_over = AsyncMock(return_value=True)
    reader = Mock(spec=ISchedulerReader)
    reader.is_wake_up_source = Mock(side_effect=lambda entity: entity == ALARM)
    reader.get_next_timeslot_of = AsyncMock(return_value=own_next)
    use_case = ScheduleAnticipationActionUseCase(
        reader, Mock(), control, anticipation_recalc_tolerance_minutes=TOLERANCE_MINUTES
    )
    return use_case, control


async def _recalc(use_case, new_slot: ScheduledTimeslot) -> None:
    await use_case._cancel_preheating_for_other_slot(new_slot.target_time, new_slot)


@pytest.mark.asyncio
async def test_a_snooze_hands_the_preheat_over_without_a_restore() -> None:
    preheating_for = NOW + timedelta(hours=1)
    snoozed = _slot(ALARM, preheating_for + timedelta(minutes=10))
    use_case, control = _build(ALARM, preheating_for, own_next=snoozed)

    await _recalc(use_case, snoozed)

    control.hand_over.assert_awaited_once_with(snoozed)
    control.cancel_preheating.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_move_by_the_tolerance_or_more_reverts() -> None:
    preheating_for = NOW + timedelta(hours=1)
    moved = _slot(ALARM, preheating_for + timedelta(minutes=TOLERANCE_MINUTES))
    use_case, control = _build(ALARM, preheating_for, own_next=moved)

    await _recalc(use_case, moved)

    control.hand_over.assert_not_awaited()
    control.cancel_preheating.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_closer_alarm_takes_over_a_schedule_preheat() -> None:
    schedule_slot = NOW + timedelta(hours=2)
    closer = _slot(ALARM, NOW + timedelta(hours=1))
    use_case, control = _build(PLAN, schedule_slot, own_next=_slot(PLAN, schedule_slot))

    await _recalc(use_case, closer)

    control.hand_over.assert_awaited_once_with(closer)
    control.cancel_preheating.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_closer_alarm_takes_over_another_alarm() -> None:
    other = "input_datetime.arrival"
    later = NOW + timedelta(hours=3)
    closer = _slot(ALARM, NOW + timedelta(hours=1))
    use_case, control = _build(other, later, own_next=_slot(other, later))

    await _recalc(use_case, closer)

    control.hand_over.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_vanished_alarm_reverts_the_preheat() -> None:
    preheating_for = NOW + timedelta(hours=1)
    schedule_slot = _slot(PLAN, NOW + timedelta(hours=2))
    use_case, control = _build(ALARM, preheating_for, own_next=None)

    await _recalc(use_case, schedule_slot)

    control.hand_over.assert_not_awaited()
    control.cancel_preheating.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_alarm_moved_after_the_schedule_slot_reverts() -> None:
    """The schedule slot is now the earliest: it is a different slot, not a moved alarm."""
    preheating_for = NOW + timedelta(hours=1)
    schedule_slot = _slot(PLAN, NOW + timedelta(hours=2))
    use_case, control = _build(
        ALARM, preheating_for, own_next=_slot(ALARM, NOW + timedelta(hours=4))
    )

    await _recalc(use_case, schedule_slot)

    control.hand_over.assert_not_awaited()
    control.cancel_preheating.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_schedulers_keep_the_existing_behavior() -> None:
    """With no wake-up source involved nothing changes: the #64 rule alone decides."""
    other = "switch.other"
    preheating_for = NOW + timedelta(hours=2)
    use_case, control = _build(
        other, preheating_for, own_next=_slot(other, preheating_for + timedelta(hours=1))
    )

    await _recalc(use_case, _slot(PLAN, NOW + timedelta(hours=1)))

    control.hand_over.assert_not_awaited()
    control.cancel_preheating.assert_awaited_once()


@pytest.mark.asyncio
async def test_without_the_readers_slot_nothing_is_handed_over() -> None:
    use_case, control = _build(ALARM, NOW + timedelta(hours=1), own_next=None)

    await use_case._cancel_preheating_for_other_slot(NOW + timedelta(hours=2), None)

    control.hand_over.assert_not_awaited()
    control.cancel_preheating.assert_awaited_once()
