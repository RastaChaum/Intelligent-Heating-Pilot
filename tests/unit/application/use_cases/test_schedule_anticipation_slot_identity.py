"""A preheat lasts only while its slot is still its scheduler's next one (#249, #64)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CancelReason,
    ScheduledTimeslot,
)

ACTIVE = "switch.active"


def _slot(when: datetime, entity: str = ACTIVE) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=when,
        target_temp=20.0,
        timeslot_id=f"{entity}_{when.isoformat()}",
        scheduler_entity=entity,
    )


def _data(next_time: datetime, entity: str) -> dict:
    return {
        "anticipated_start_time": next_time - timedelta(hours=1),
        "next_schedule_time": next_time,
        "next_target_temperature": 20.0,
        "scheduler_entity": entity,
        "learned_heating_slope": 2.0,
        "anticipation_minutes": 60,
        "current_temp": 17.0,
    }


async def _preheating_for(
    use_case, control, reader, slot: datetime, own_next: ScheduledTimeslot | None
):
    use_case._control_preheating = control
    reader.is_scheduler_enabled = AsyncMock(
        return_value=True
    )  # an enabled scheduler proves nothing
    reader.get_next_timeslot_of = AsyncMock(return_value=own_next)
    await control.start_preheating(target_time=slot, target_temp=20.0, scheduler_entity_id=ACTIVE)
    control._preheat_actuator.cancel = AsyncMock()


@pytest.mark.asyncio
async def test_a_moved_slot_reverts_the_preheat_even_though_the_scheduler_is_enabled(
    schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
    control_preheating_use_case,
    scheduler_reader,
    test_now: datetime,
) -> None:
    preheated = test_now + timedelta(minutes=30)
    moved_to = test_now + timedelta(hours=3)
    with patch.object(dt_util, "now", return_value=test_now):
        await _preheating_for(
            schedule_anticipation_action_use_case,
            control_preheating_use_case,
            scheduler_reader,
            preheated,
            own_next=_slot(moved_to),
        )

        await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
            _data(moved_to, ACTIVE), ihp_enabled=True
        )

    cancel = control_preheating_use_case._preheat_actuator.cancel
    cancel.assert_awaited_once()
    assert cancel.await_args.args[1] is CancelReason.SLOT_CHANGED
    assert control_preheating_use_case.is_preheating_active() is False


@pytest.mark.asyncio
async def test_a_removed_slot_reverts_the_preheat(
    schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
    control_preheating_use_case,
    scheduler_reader,
    test_now: datetime,
) -> None:
    preheated = test_now + timedelta(minutes=30)
    later = test_now + timedelta(hours=10)
    with patch.object(dt_util, "now", return_value=test_now):
        await _preheating_for(
            schedule_anticipation_action_use_case,
            control_preheating_use_case,
            scheduler_reader,
            preheated,
            own_next=None,  # the scheduler no longer has the slot
        )

        await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
            _data(later, "switch.other"), ihp_enabled=True
        )

    control_preheating_use_case._preheat_actuator.cancel.assert_awaited_once()
    assert control_preheating_use_case.is_preheating_active() is False


@pytest.mark.asyncio
async def test_an_earlier_candidate_of_another_scheduler_does_not_revert_the_preheat(
    schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
    control_preheating_use_case,
    scheduler_reader,
    test_now: datetime,
) -> None:
    """The #64 flap: the earliest candidate differs, but the preheated slot is still its own."""
    preheated = test_now + timedelta(minutes=30)
    with patch.object(dt_util, "now", return_value=test_now):
        await _preheating_for(
            schedule_anticipation_action_use_case,
            control_preheating_use_case,
            scheduler_reader,
            preheated,
            own_next=_slot(preheated),
        )

        await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
            _data(test_now + timedelta(minutes=5), "switch.earlier"), ihp_enabled=True
        )

    control_preheating_use_case._preheat_actuator.cancel.assert_not_awaited()
    assert control_preheating_use_case.is_preheating_active() is True


@pytest.mark.asyncio
async def test_a_direct_command_without_effect_never_falls_back_and_is_tried_again(
    schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
    scheduler_reader,
    test_now: datetime,
) -> None:
    """Clarification 3: retry at the next recalculation, with no other scheduler tried."""
    from unittest.mock import Mock

    from custom_components.intelligent_heating_pilot.application.use_cases import (
        ControlPreheatingUseCase,
    )
    from custom_components.intelligent_heating_pilot.domain.value_objects import ActuationResult

    actuator = Mock()
    actuator.start = AsyncMock(return_value=ActuationResult.NOT_APPLIED)
    control = ControlPreheatingUseCase(actuator)
    use_case = schedule_anticipation_action_use_case
    use_case._control_preheating = control
    scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)
    slot = test_now + timedelta(minutes=30)

    with patch.object(dt_util, "now", return_value=test_now):
        results = [
            await use_case.schedule_action(
                anticipated_start=test_now - timedelta(minutes=5),
                target_time=slot,
                target_temp=20.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )
            for _ in range(2)
        ]

    assert results == [None, None]  # never reported as blocked: no fallback candidate is tried
    assert actuator.start.await_count == 2  # tried again at the next recalculation
    assert control.is_preheating_active() is False
