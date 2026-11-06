"""Tests for ScheduleAnticipationActionUseCase.

Tests verify complex scheduling logic including:
- Timer scheduling for future starts
- Immediate preheating when start is in the past
- Revert logic when LHS improves
- Scheduler disabled detection
- IHP enabled/disabled handling
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)


class TestScheduleAnticipationActionHandleAnticipation:
    """Test handle_anticipation_scheduling() - the main orchestration method."""

    @pytest.mark.asyncio
    async def test_no_data_cancels_everything(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        test_now: datetime,
    ) -> None:
        """Test that missing data cancels all preheating.

        GIVEN: No valid anticipation data
        WHEN: handle_anticipation_scheduling called
        THEN: Preheating and timers are cancelled
        """
        # GIVEN: Empty (no start time)
        anticipation_data = {
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "scheduler_entity": "schedule.test",
        }

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data=anticipation_data,
                ihp_enabled=True,
            )

        # THEN: No timer scheduled
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore

    @pytest.mark.asyncio
    async def test_ihp_disabled_cancels_preheating(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        test_now: datetime,
    ) -> None:
        """Test that IHP disabled cancels preheating.

        GIVEN: Valid data but IHP disabled
        WHEN: handle_anticipation_scheduling called
        THEN: Preheating is cancelled
        """
        # GIVEN
        target_time = test_now + timedelta(hours=1, minutes=30)
        anticipation_data = {
            "anticipated_start_time": test_now + timedelta(hours=1),
            "next_schedule_time": target_time,
            "next_target_temperature": 21.0,
            "scheduler_entity": "schedule.test",
            "learned_heating_slope": 2.0,
            "anticipation_minutes": 30,
        }

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data=anticipation_data,
                ihp_enabled=False,  # IHP disabled
            )

        # THEN: No timer scheduled because IHP disabled
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore

    @pytest.mark.asyncio
    async def test_no_scheduler_entity_skips_scheduling(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        test_now: datetime,
    ) -> None:
        """Test that missing scheduler entity is skipped.

        GIVEN: Valid data but no scheduler entity
        WHEN: handle_anticipation_scheduling called
        THEN: No timer scheduled
        """
        # GIVEN
        anticipation_data = {
            "anticipated_start_time": test_now + timedelta(hours=1),
            "next_schedule_time": test_now + timedelta(hours=1, minutes=30),
            "next_target_temperature": 21.0,
            "scheduler_entity": None,  # No scheduler!
        }

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data=anticipation_data,
                ihp_enabled=True,
            )

        # THEN: No timer scheduled
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore

    @pytest.mark.asyncio
    async def test_valid_data_schedules_timer(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that valid data schedules a timer.

        GIVEN: Valid data, IHP enabled, scheduler enabled
        WHEN: handle_anticipation_scheduling called
        THEN: Timer is scheduled for anticipated start time
        """
        # GIVEN: Mock scheduler enabled and dt_util.now()
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        target_time = test_now + timedelta(hours=1, minutes=30)
        anticipated_start = test_now + timedelta(hours=1)
        anticipation_data = {
            "anticipated_start_time": anticipated_start,
            "next_schedule_time": target_time,
            "next_target_temperature": 21.0,
            "scheduler_entity": "schedule.heating",
            "learned_heating_slope": 2.0,
            "anticipation_minutes": 30,
        }

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data=anticipation_data,
                ihp_enabled=True,
            )

        # THEN: Timer scheduled
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert len(timer_scheduler.scheduled_timers) >= 1  # type: ignore
        scheduled_time, _ = timer_scheduler.scheduled_timers[0]  # type: ignore
        assert scheduled_time == anticipated_start


class TestScheduleAnticipationActionScheduling:
    """Test schedule_action() - timer scheduling and immediate triggers."""

    @pytest.mark.asyncio
    async def test_immediate_trigger_when_start_in_past(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that start in past triggers preheating immediately.

        GIVEN: Anticipated start in past, target in future
        WHEN: schedule_action called
        THEN: No timer scheduled (immediate trigger)
        """
        # GIVEN
        anticipated_start = test_now - timedelta(minutes=5)  # 5 minutes ago
        target_time = test_now + timedelta(hours=1)
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        assert not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

        # THEN: Preheating triggered (no timer scheduled)
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore
        assert schedule_anticipation_action_use_case._control_preheating.is_preheating_active()

    @pytest.mark.asyncio
    async def test_both_times_in_past_skips(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that both times in past is skipped.

        GIVEN: Both start and target in past
        WHEN: schedule_action called
        THEN: Nothing happens (no timer scheduled)
        """
        # GIVEN
        anticipated_start = test_now - timedelta(hours=1)
        target_time = test_now - timedelta(minutes=30)
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            # THEN: Nothing scheduled
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore
            assert (
                not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            )

    @pytest.mark.asyncio
    async def test_future_start_schedules_timer(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that future start schedules a timer.

        GIVEN: Both times in future
        WHEN: schedule_action called
        THEN: Timer scheduled for anticipated start time
        """
        # GIVEN
        anticipated_start = test_now + timedelta(hours=1)
        target_time = test_now + timedelta(hours=1, minutes=30)
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            # THEN: Timer scheduled
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 1  # type: ignore
            scheduled_time, _ = timer_scheduler.scheduled_timers[0]  # type: ignore
            assert scheduled_time == anticipated_start

    @pytest.mark.asyncio
    async def test_scheduler_disabled_skips(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that disabled scheduler is skipped.

        GIVEN: Scheduler disabled
        WHEN: schedule_action called
        THEN: No timer or preheating triggered
        """
        # GIVEN
        anticipated_start = test_now + timedelta(hours=1)
        target_time = test_now + timedelta(hours=1, minutes=30)
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=False)

        # WHEN
        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            # THEN: Nothing scheduled
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore
            assert (
                not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            )


class TestScheduleAnticipationActionRevertLogic:
    """Test revert logic when anticipated time changes significantly."""

    @pytest.mark.asyncio
    async def test_significant_time_shift_reverts_and_reschedules(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that a significant anticipated-time shift reverts and reschedules.

        GIVEN: Preheating active with old start time, new start is later
        WHEN: schedule_action called with a delta >= threshold
        THEN: Preheating is reverted and new timer scheduled for new start time
        """
        # GIVEN: Start preheating with initial timing
        initial_target = test_now + timedelta(hours=2)
        with patch.object(dt_util, "now", return_value=test_now):
            schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
            await control_preheating_use_case.start_preheating(
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
            )

            # Verify preheating is active
            assert schedule_anticipation_action_use_case._control_preheating.is_preheating_active()

            # Manually set previous scheduling tracking
            schedule_anticipation_action_use_case._last_scheduled_time = test_now + timedelta(
                hours=1
            )
            schedule_anticipation_action_use_case._last_scheduled_lhs = 1.0  # Old LHS
            schedule_anticipation_action_use_case._anticipation_recalc_tolerance_seconds = 15 * 60

            # Mock scheduler state
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

            # WHEN: New calculation with significant time delta (20 minutes)
            new_anticipated_start = test_now + timedelta(hours=1, minutes=20)
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=new_anticipated_start,
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            # THEN: Preheating reverted and new timer scheduled for new start time
            assert (
                not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            )
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 1  # type: ignore
            scheduled_time, _ = timer_scheduler.scheduled_timers[0]  # type: ignore
            assert scheduled_time == new_anticipated_start

    @pytest.mark.asyncio
    async def test_small_time_shift_keeps_active_preheating(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Do not revert active preheating when time delta is below threshold."""
        initial_target = test_now + timedelta(hours=2)

        with patch.object(dt_util, "now", return_value=test_now):
            schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
            await control_preheating_use_case.start_preheating(
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
            )

            schedule_anticipation_action_use_case._last_scheduled_time = test_now + timedelta(
                hours=1
            )
            schedule_anticipation_action_use_case._anticipation_recalc_tolerance_seconds = 15 * 60
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now + timedelta(hours=1, minutes=5),  # 5 minutes shift
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            assert schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore

    @pytest.mark.asyncio
    async def test_threshold_boundary_reverts_when_delta_equals_threshold(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Revert must trigger when delta is exactly equal to the configured threshold."""
        initial_target = test_now + timedelta(hours=2)

        with patch.object(dt_util, "now", return_value=test_now):
            schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
            await control_preheating_use_case.start_preheating(
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
            )

            schedule_anticipation_action_use_case._last_scheduled_time = test_now + timedelta(
                hours=1
            )
            schedule_anticipation_action_use_case._anticipation_recalc_tolerance_seconds = 15 * 60
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now + timedelta(hours=1, minutes=15),
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            assert (
                not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            )
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 1  # type: ignore

    @pytest.mark.asyncio
    async def test_earlier_time_does_not_revert_when_preheating_is_active(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Do not revert when anticipated start moves earlier while preheating is active."""
        initial_target = test_now + timedelta(hours=2)

        with patch.object(dt_util, "now", return_value=test_now):
            schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
            await control_preheating_use_case.start_preheating(
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
            )

            schedule_anticipation_action_use_case._last_scheduled_time = test_now + timedelta(
                hours=1
            )
            schedule_anticipation_action_use_case._anticipation_recalc_tolerance_seconds = 15 * 60
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now + timedelta(minutes=40),  # moved earlier by 20 minutes
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

            assert schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 0  # type: ignore


class TestCancelPreheatingForOtherSlotStability:
    """Regression test for a flap discovered while implementing #64's fallback.

    The earliest-scheduler-first retry recomputes "next timeslot" from scratch
    every cycle, so a fresh calculation can show a different (earlier, still
    blocked) candidate even while a successful fallback is actively
    preheating. _cancel_preheating_for_other_slot must not revert that active
    preheat just because this tick's freshly computed candidate differs -
    only when the active scheduler is no longer usable at all.
    """

    @pytest.mark.asyncio
    async def test_active_scheduler_still_enabled_is_not_reverted(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A different, earlier candidate this tick must not revert a still-valid
        active preheat for a different scheduler (the #64 flap finding)."""
        schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        with patch.object(dt_util, "now", return_value=test_now):
            await control_preheating_use_case.start_preheating(
                target_time=test_now + timedelta(minutes=30),
                target_temp=20.0,
                scheduler_entity_id="switch.vacation",
            )
            control_preheating_use_case._scheduler_commander.cancel_action = AsyncMock()

            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data={
                    "anticipated_start_time": test_now,
                    "next_schedule_time": test_now + timedelta(minutes=5),
                    "next_target_temperature": 20.0,
                    "scheduler_entity": "switch.non_vacation",
                    "learned_heating_slope": 2.0,
                    "anticipation_minutes": 5,
                    "current_temp": 17.0,
                },
                ihp_enabled=True,
            )

        control_preheating_use_case._scheduler_commander.cancel_action.assert_not_awaited()
        assert control_preheating_use_case.is_preheating_active() is True
        assert control_preheating_use_case.get_active_scheduler_entity() == "switch.vacation"

    @pytest.mark.asyncio
    async def test_active_scheduler_no_longer_enabled_is_still_reverted(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A genuinely disabled/removed active scheduler is still reverted -
        the pre-existing #182 anti-flap behavior must not regress."""
        schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        with patch.object(dt_util, "now", return_value=test_now):
            await control_preheating_use_case.start_preheating(
                target_time=test_now + timedelta(minutes=30),
                target_temp=20.0,
                scheduler_entity_id="switch.vacation",
            )
            control_preheating_use_case._scheduler_commander.cancel_action = AsyncMock()
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=False)

            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data={
                    "anticipated_start_time": test_now,
                    "next_schedule_time": test_now + timedelta(minutes=5),
                    "next_target_temperature": 20.0,
                    "scheduler_entity": "switch.non_vacation",
                    "learned_heating_slope": 2.0,
                    "anticipation_minutes": 5,
                    "current_temp": 17.0,
                },
                ihp_enabled=True,
            )

        control_preheating_use_case._scheduler_commander.cancel_action.assert_awaited_once_with(
            "switch.vacation"
        )
        assert control_preheating_use_case.is_preheating_active() is False


class TestScheduleAnticipationActionStateTransitions:
    """Test preheating state transitions around target reached and slot completion."""

    @pytest.mark.asyncio
    async def test_completed_preheating_does_not_block_next_slot(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A preheat whose slot has passed must not prevent anticipating the next slot.

        GIVEN: Preheating was started for a slot that fired 5 minutes ago
        WHEN: A recalculation targets the next slot, 10 hours ahead
        THEN: The old preheat is marked complete without reverting the thermostat,
              and a timer is scheduled for the next slot's anticipated start
        """
        past_target = test_now - timedelta(minutes=5)
        next_target = test_now + timedelta(hours=10)
        next_start = next_target - timedelta(hours=1)
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)
        schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case

        with patch.object(dt_util, "now", return_value=test_now):
            await control_preheating_use_case.start_preheating(
                target_time=past_target,
                target_temp=19.0,
                scheduler_entity_id="schedule.heating",
            )
            control_preheating_use_case._scheduler_commander.cancel_action = AsyncMock()

            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data={
                    "anticipated_start_time": next_start,
                    "next_schedule_time": next_target,
                    "next_target_temperature": 20.0,
                    "scheduler_entity": "schedule.heating",
                    "learned_heating_slope": 2.0,
                    "anticipation_minutes": 60,
                },
                ihp_enabled=True,
            )

        assert not control_preheating_use_case.is_preheating_active()
        control_preheating_use_case._scheduler_commander.cancel_action.assert_not_awaited()
        timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
        assert [t for t, _ in timer_scheduler.scheduled_timers] == [next_start]  # type: ignore

    @pytest.mark.asyncio
    async def test_target_reached_without_active_preheating_cancels_timer(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        test_now: datetime,
    ) -> None:
        """A pending timer is dropped when the room is already at target."""
        cancel_timer = Mock()
        schedule_anticipation_action_use_case._anticipation_timer_cancel = cancel_timer

        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data={
                    "anticipated_start_time": test_now + timedelta(hours=2),
                    "next_schedule_time": test_now + timedelta(hours=2),
                    "next_target_temperature": 20.0,
                    "scheduler_entity": "schedule.heating",
                    "anticipation_minutes": 0,
                    "current_temp": 20.5,
                },
                ihp_enabled=True,
            )

        cancel_timer.assert_called_once()

    @pytest.mark.asyncio
    async def test_preheating_for_removed_slot_is_reverted(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        test_now: datetime,
    ) -> None:
        """An active preheat is reverted once its slot is no longer the next one.

        GIVEN: Preheating is active for a slot 1 hour ahead
        WHEN: The next slot becomes another one, already at target
        THEN: The thermostat is reverted and preheating is inactive
        """
        schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case

        with patch.object(dt_util, "now", return_value=test_now):
            await control_preheating_use_case.start_preheating(
                target_time=test_now + timedelta(hours=1),
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
            )
            control_preheating_use_case._scheduler_commander.cancel_action = AsyncMock()

            await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data={
                    "anticipated_start_time": test_now + timedelta(hours=10),
                    "next_schedule_time": test_now + timedelta(hours=10),
                    "next_target_temperature": 19.0,
                    "scheduler_entity": "schedule.heating",
                    "anticipation_minutes": 0,
                    "current_temp": 21.0,
                },
                ihp_enabled=True,
            )

        assert not control_preheating_use_case.is_preheating_active()
        control_preheating_use_case._scheduler_commander.cancel_action.assert_awaited_once_with(
            "schedule.heating"
        )

    @pytest.mark.asyncio
    async def test_immediate_start_cancels_pending_timer(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A timer left from an earlier calculation must not fire during the preheat."""
        cancel_timer = Mock()
        schedule_anticipation_action_use_case._anticipation_timer_cancel = cancel_timer
        schedule_anticipation_action_use_case._control_preheating = control_preheating_use_case
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        with patch.object(dt_util, "now", return_value=test_now):
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now - timedelta(minutes=5),
                target_time=test_now + timedelta(hours=1),
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,
            )

        cancel_timer.assert_called_once()
        assert control_preheating_use_case.is_preheating_active()


class TestScheduleAnticipationActionBlockedPropagation:
    """Tests for surfacing a confirmed-blocked scheduler to the caller (#64).

    ``start_preheating()`` now returns a bool; these tests verify
    ``schedule_action()``/``_trigger_action()``/``handle_anticipation_scheduling()``
    propagate a blocked entity id (instead of swallowing it) so the caller
    (``HeatingOrchestrator``) can attempt a fallback candidate.
    """

    def _mock_control_preheating(self, start_preheating_result: bool) -> Mock:
        control = Mock()
        control.start_preheating = AsyncMock(return_value=start_preheating_result)
        control.is_preheating_active = Mock(return_value=False)
        control.get_preheating_target_time = Mock(return_value=None)
        control.get_active_scheduler_entity = Mock(return_value=None)
        control.cancel_preheating = AsyncMock()
        return control

    @pytest.mark.asyncio
    async def test_schedule_action_immediate_trigger_returns_blocked_entity_on_false(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A confirmed-blocked immediate trigger returns the scheduler's entity id."""
        schedule_anticipation_action_use_case._control_preheating = self._mock_control_preheating(
            False
        )
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        with patch.object(dt_util, "now", return_value=test_now):
            result = await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now - timedelta(minutes=5),
                target_time=test_now + timedelta(hours=1),
                target_temp=21.0,
                scheduler_entity_id="switch.non_vacation",
                lhs=2.0,
            )

        assert result == "switch.non_vacation"

    @pytest.mark.asyncio
    async def test_schedule_action_immediate_trigger_returns_none_on_confirmed_success(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A confirmed-successful immediate trigger returns None (no fallback needed)."""
        schedule_anticipation_action_use_case._control_preheating = self._mock_control_preheating(
            True
        )
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        with patch.object(dt_util, "now", return_value=test_now):
            result = await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=test_now - timedelta(minutes=5),
                target_time=test_now + timedelta(hours=1),
                target_temp=21.0,
                scheduler_entity_id="switch.non_vacation",
                lhs=2.0,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_timer_fired_trigger_returns_blocked_entity_on_false(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """A confirmed-blocked action when the anticipation timer fires is surfaced too."""
        schedule_anticipation_action_use_case._control_preheating = self._mock_control_preheating(
            False
        )
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

        result = await schedule_anticipation_action_use_case._trigger_action(
            target_time=test_now + timedelta(hours=1),
            target_temp=21.0,
            scheduler_entity_id="switch.non_vacation",
        )

        assert result == "switch.non_vacation"

    @pytest.mark.asyncio
    async def test_handle_anticipation_scheduling_propagates_blocked_entity(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """The top-level entry point also surfaces the blocked entity id to its caller."""
        schedule_anticipation_action_use_case._control_preheating = self._mock_control_preheating(
            False
        )
        scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)
        anticipation_data = {
            "anticipated_start_time": test_now - timedelta(minutes=5),
            "next_schedule_time": test_now + timedelta(hours=1),
            "next_target_temperature": 21.0,
            "scheduler_entity": "switch.non_vacation",
            "learned_heating_slope": 2.0,
            "anticipation_minutes": 30,
        }

        with patch.object(dt_util, "now", return_value=test_now):
            result = await schedule_anticipation_action_use_case.handle_anticipation_scheduling(
                anticipation_data=anticipation_data,
                ihp_enabled=True,
            )

        assert result == "switch.non_vacation"
