"""Unit tests for scheduling anticipation actions.

Tests the timer-based anticipation triggering mechanism that ensures
preheating triggers at the anticipated start time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def mock_scheduler_reader() -> Mock:
    """Create a mock scheduler reader."""
    reader = Mock()
    reader.is_scheduler_enabled = AsyncMock(return_value=True)
    return reader


@pytest.fixture
def mock_scheduler_commander() -> Mock:
    """Create a mock scheduler commander."""
    commander = Mock()
    commander.run_action = AsyncMock()
    commander.cancel_action = AsyncMock()
    return commander


@pytest.fixture
def mock_timer_scheduler() -> Mock:
    """Create a mock timer scheduler."""
    scheduler = Mock()
    scheduler.schedule_timer = Mock(return_value=Mock())
    return scheduler


@pytest.fixture
def use_case(
    mock_scheduler_reader: Mock,
    mock_scheduler_commander: Mock,
    mock_timer_scheduler: Mock,
) -> ScheduleAnticipationActionUseCase:
    """Create ScheduleAnticipationActionUseCase with mocked dependencies."""
    return ScheduleAnticipationActionUseCase(
        scheduler_reader=mock_scheduler_reader,
        scheduler_commander=mock_scheduler_commander,
        timer_scheduler=mock_timer_scheduler,
    )


class TestAnticipationTimer:
    """Test suite for timer-based anticipation mechanism."""

    @pytest.mark.asyncio
    async def test_timer_scheduled_for_future_anticipation(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_scheduler_commander: Mock,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test that a timer is scheduled when anticipated start is in the future."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        anticipated_start = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=2.0,
            )

        assert mock_timer_scheduler.schedule_timer.called
        mock_scheduler_commander.run_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_timer_rescheduled_when_anticipated_start_updates(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test timer reschedules when anticipated start time changes."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        first_start = make_aware(datetime(2025, 1, 15, 5, 0, 0))
        second_start = make_aware(datetime(2025, 1, 15, 4, 30, 0))

        cancel_first = Mock()
        cancel_second = Mock()
        mock_timer_scheduler.schedule_timer.side_effect = [cancel_first, cancel_second]

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=first_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=1.5,
            )
            await use_case.schedule_action(
                anticipated_start=second_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=1.6,
            )

        assert mock_timer_scheduler.schedule_timer.call_count == 2
        assert cancel_first.called
        assert not cancel_second.called

    @pytest.mark.asyncio
    async def test_immediate_trigger_when_anticipation_in_past(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_scheduler_commander: Mock,
    ) -> None:
        """Test that action is triggered immediately when anticipated start is in the past."""
        now = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        anticipated_start = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=2.0,
            )

        mock_scheduler_commander.run_action.assert_called_once_with(
            target_time,
            "switch.test_scheduler",
        )
        is_active, active_target_time, _ = use_case.get_preheating_state()
        assert is_active is True
        assert active_target_time == target_time

    @pytest.mark.asyncio
    async def test_timer_cancelled_when_state_cleared(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test that timer is cancelled when anticipation state is cleared."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        anticipated_start = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        cancel_callback = Mock()
        mock_timer_scheduler.schedule_timer.return_value = cancel_callback

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=2.0,
            )

        await use_case._clear_state()

        cancel_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_timer_cancelled_when_scheduler_disabled(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_scheduler_reader: Mock,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test that timer is cancelled when scheduler is disabled."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        anticipated_start = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        cancel_callback = Mock()
        mock_timer_scheduler.schedule_timer.return_value = cancel_callback

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=2.0,
            )

        mock_scheduler_reader.is_scheduler_enabled.return_value = False

        with patch.object(dt_util, "now", return_value=now):
            await use_case.schedule_action(
                anticipated_start=anticipated_start,
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id="switch.test_scheduler",
                lhs=2.0,
            )

        cancel_callback.assert_called_once()
        assert use_case.get_preheating_state() == (False, None, None)
