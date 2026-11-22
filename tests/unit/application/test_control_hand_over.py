"""ControlPreheatingUseCase.hand_over: the preheat is active only if the actuator confirmed it."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import IPreheatActuator
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    ScheduledTimeslot,
    SlotAction,
)

SLOT = ScheduledTimeslot(
    target_time=datetime(2026, 11, 16, 6, 30, tzinfo=UTC),
    target_temp=21.0,
    timeslot_id="sensor.alarm_2026-11-16",
    scheduler_entity="sensor.alarm",
    action=SlotAction(preset="comfort"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "active"),
    [
        (ActuationResult.APPLIED, True),
        (ActuationResult.SKIPPED, True),
        (ActuationResult.NOT_APPLIED, False),
        (ActuationResult.UNSUPPORTED, False),
    ],
)
async def test_the_preheat_is_active_only_when_the_hand_over_took(result, active) -> None:
    actuator = Mock(spec=IPreheatActuator)
    actuator.hand_over = AsyncMock(return_value=result)
    use_case = ControlPreheatingUseCase(actuator, Mock())

    await use_case.hand_over(SLOT)

    assert use_case.is_preheating_active() is active
    assert use_case.get_preheating_target_time() == SLOT.target_time
    assert use_case.get_active_scheduler_entity() == "sensor.alarm"
