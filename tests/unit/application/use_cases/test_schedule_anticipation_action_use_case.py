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
from unittest.mock import AsyncMock, patch

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
    """Test revert logic when LHS improves during active preheating."""

    @pytest.mark.asyncio
    async def test_lhs_improvement_reverts_and_reschedules(
        self,
        schedule_anticipation_action_use_case: ScheduleAnticipationActionUseCase,
        control_preheating_use_case,
        scheduler_reader,
        test_now: datetime,
    ) -> None:
        """Test that LHS improvement triggers revert and reschedule.

        GIVEN: Preheating active with old start time, new start is later
        WHEN: schedule_action called with improved LHS
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

            # Manually set LHS tracking
            schedule_anticipation_action_use_case._last_scheduled_time = test_now + timedelta(
                hours=1
            )
            schedule_anticipation_action_use_case._last_scheduled_lhs = 1.0  # Old LHS

            # Mock scheduler state
            scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

            # WHEN: New calculation with improved LHS
            new_anticipated_start = test_now + timedelta(hours=1, minutes=10)
            await schedule_anticipation_action_use_case.schedule_action(
                anticipated_start=new_anticipated_start,
                target_time=initial_target,
                target_temp=21.0,
                scheduler_entity_id="schedule.heating",
                lhs=2.0,  # Improved!
            )

            # THEN: Preheating reverted and new timer scheduled for new start time
            assert (
                not schedule_anticipation_action_use_case._control_preheating.is_preheating_active()
            )
            timer_scheduler = schedule_anticipation_action_use_case._timer_scheduler
            assert len(timer_scheduler.scheduled_timers) == 1  # type: ignore
            scheduled_time, _ = timer_scheduler.scheduled_timers[0]  # type: ignore
            assert scheduled_time == new_anticipated_start
