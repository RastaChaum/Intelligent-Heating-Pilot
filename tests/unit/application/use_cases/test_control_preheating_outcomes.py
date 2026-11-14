"""Unit tests for how ControlPreheatingUseCase turns an actuator result into a preheat state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    CancelReason,
    ScheduledTimeslot,
    SlotAction,
)

MODULE = (
    "custom_components.intelligent_heating_pilot.application.use_cases.control_preheating_use_case"
)
SLOT = datetime(2025, 2, 10, 7, 0, tzinfo=UTC)
ENTITY = "schedule.heating"


def _use_case(result: ActuationResult) -> tuple[ControlPreheatingUseCase, Mock]:
    actuator = Mock()
    actuator.start = AsyncMock(return_value=result)
    actuator.cancel = AsyncMock()
    actuator.recover = AsyncMock(return_value=False)
    return ControlPreheatingUseCase(actuator), actuator


async def _start(use_case: ControlPreheatingUseCase, action: SlotAction | None = None) -> bool:
    return await use_case.start_preheating(SLOT, 21.0, ENTITY, action=action)


class TestResults:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("result", [ActuationResult.APPLIED, ActuationResult.UNSUPPORTED])
    async def test_an_applied_or_compute_only_start_is_active(self, result) -> None:
        use_case, _ = _use_case(result)

        assert await _start(use_case) is True
        assert use_case.is_preheating_active() is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("result", [ActuationResult.NOT_APPLIED, ActuationResult.SKIPPED])
    async def test_a_command_without_effect_is_not_blocked_and_not_active(self, result) -> None:
        """Nothing to fall back on, and nothing started: the next recalculation tries again."""
        use_case, _ = _use_case(result)

        assert await _start(use_case) is True
        assert use_case.is_preheating_active() is False

    @pytest.mark.asyncio
    async def test_the_action_reaches_the_actuator_with_the_slot(self) -> None:
        use_case, actuator = _use_case(ActuationResult.APPLIED)

        await _start(use_case, SlotAction(preset="comfort"))

        slot: ScheduledTimeslot = actuator.start.call_args.args[0]
        assert slot.action == SlotAction(preset="comfort")
        assert slot.scheduler_entity == ENTITY
        assert slot.target_time == SLOT


class TestNoEffectReport:
    @pytest.mark.asyncio
    async def test_a_command_without_effect_is_reported_once_per_slot_at_info(self, caplog) -> None:
        use_case, _ = _use_case(ActuationResult.NOT_APPLIED)

        with caplog.at_level(logging.DEBUG, logger=MODULE):
            await _start(use_case)
            await _start(use_case)
            await _start(use_case)

        infos = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "did not take" in r.getMessage()
        ]
        assert len(infos) == 1

    @pytest.mark.asyncio
    async def test_the_report_is_made_again_for_another_slot(self, caplog) -> None:
        use_case, _ = _use_case(ActuationResult.NOT_APPLIED)

        with caplog.at_level(logging.INFO, logger=MODULE):
            await use_case.start_preheating(SLOT, 21.0, ENTITY)
            await use_case.start_preheating(SLOT.replace(hour=9), 21.0, ENTITY)

        infos = [r for r in caplog.records if "did not take" in r.getMessage()]
        assert len(infos) == 2

    @pytest.mark.asyncio
    async def test_a_guard_that_stops_the_command_stays_at_debug(self, caplog) -> None:
        use_case, _ = _use_case(ActuationResult.SKIPPED)

        with caplog.at_level(logging.DEBUG, logger=MODULE):
            await _start(use_case)

        assert [r for r in caplog.records if r.levelno >= logging.INFO] == [
            r
            for r in caplog.records
            if r.levelno >= logging.INFO and "Starting preheating" in r.getMessage()
        ]


class TestCompletion:
    @pytest.mark.asyncio
    async def test_completing_tells_the_actuator_the_slot_was_reached(self) -> None:
        use_case, actuator = _use_case(ActuationResult.APPLIED)
        await _start(use_case)

        await use_case.mark_preheating_complete()

        actuator.cancel.assert_awaited_once()
        assert actuator.cancel.await_args.args[1] is CancelReason.SLOT_REACHED
        assert use_case.is_preheating_active() is False

    @pytest.mark.asyncio
    async def test_completing_without_an_active_preheat_tells_nobody(self) -> None:
        use_case, actuator = _use_case(ActuationResult.APPLIED)

        await use_case.mark_preheating_complete()

        actuator.cancel.assert_not_awaited()


class TestRecover:
    SLOT_OBJECT = ScheduledTimeslot(
        target_time=SLOT, target_temp=21.0, timeslot_id="slot", scheduler_entity=ENTITY
    )

    @pytest.mark.asyncio
    async def test_a_preheat_in_progress_is_marked_active_again(self) -> None:
        use_case, actuator = _use_case(ActuationResult.APPLIED)
        actuator.recover = AsyncMock(return_value=True)

        await use_case.recover_preheating(self.SLOT_OBJECT)

        assert use_case.is_preheating_active() is True
        assert use_case.get_preheating_target_time() == SLOT
        assert use_case.get_active_scheduler_entity() == ENTITY

    @pytest.mark.asyncio
    async def test_nothing_in_progress_leaves_the_preheat_inactive(self) -> None:
        use_case, _ = _use_case(ActuationResult.APPLIED)

        await use_case.recover_preheating(self.SLOT_OBJECT)

        assert use_case.is_preheating_active() is False

    @pytest.mark.asyncio
    async def test_a_recovered_preheat_can_later_be_cancelled(self) -> None:
        use_case, actuator = _use_case(ActuationResult.APPLIED)
        actuator.recover = AsyncMock(return_value=True)
        await use_case.recover_preheating(self.SLOT_OBJECT)

        await use_case.cancel_preheating()

        actuator.cancel.assert_awaited_once()
        assert actuator.cancel.await_args.args[0] == self.SLOT_OBJECT
