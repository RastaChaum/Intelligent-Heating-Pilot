"""Unit tests for scheduling and overshoot use cases.

Tests that the scheduling use case handles revert logic and that the overshoot
use case detects risks correctly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application.use_cases import (
    CheckOvershootRiskUseCase,
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import ScheduledTimeslot


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def scheduler_reader() -> Mock:
    """Create mock scheduler reader."""
    reader = Mock()
    reader.get_next_timeslot = AsyncMock()
    reader.is_scheduler_enabled = AsyncMock(return_value=True)
    return reader


@pytest.fixture
def scheduler_commander() -> Mock:
    """Create mock scheduler commander."""
    commander = Mock()
    commander.run_action = AsyncMock()
    commander.cancel_action = AsyncMock()
    return commander


@pytest.fixture
def timer_scheduler() -> Mock:
    """Create mock timer scheduler."""
    scheduler = Mock()
    scheduler.schedule_timer = Mock(return_value=Mock())
    return scheduler


@pytest.fixture
def schedule_use_case(
    scheduler_reader: Mock,
    scheduler_commander: Mock,
    timer_scheduler: Mock,
) -> ScheduleAnticipationActionUseCase:
    """Create ScheduleAnticipationActionUseCase with mocked dependencies."""
    return ScheduleAnticipationActionUseCase(
        scheduler_reader=scheduler_reader,
        scheduler_commander=scheduler_commander,
        timer_scheduler=timer_scheduler,
    )


@pytest.fixture
def overshoot_use_case(scheduler_reader: Mock) -> CheckOvershootRiskUseCase:
    """Create CheckOvershootRiskUseCase with mocked dependencies."""
    return CheckOvershootRiskUseCase(scheduler_reader=scheduler_reader)


class TestRevertLogicWhenAnticipatedStartMoves:
    """Test suite for revert behavior when anticipated start time changes."""

    @pytest.mark.asyncio
    async def test_revert_when_anticipated_start_moves_later(
        self,
        schedule_use_case: ScheduleAnticipationActionUseCase,
        scheduler_commander: Mock,
    ) -> None:
        """Revert to scheduled state when anticipated start moves later."""
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        scheduler_id = "schedule.heating"

        with patch.object(dt_util, "now", return_value=base_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.8,
            )

        scheduler_commander.run_action.assert_called_once()
        is_active, active_target_time, _ = schedule_use_case.get_preheating_state()
        assert is_active is True
        assert active_target_time == target_time

        later_time = make_aware(datetime(2025, 1, 15, 4, 45, 0))
        scheduler_commander.run_action.reset_mock()

        with patch.object(dt_util, "now", return_value=later_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 5, 0, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=4.0,
            )

        scheduler_commander.cancel_action.assert_called_once()
        is_active, active_target_time, _ = schedule_use_case.get_preheating_state()
        assert is_active is False
        assert active_target_time is None
        scheduler_commander.run_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_heating_when_still_needed(
        self,
        schedule_use_case: ScheduleAnticipationActionUseCase,
        scheduler_commander: Mock,
    ) -> None:
        """Continue heating when anticipated start is still in the past."""
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        scheduler_id = "schedule.heating"

        with patch.object(dt_util, "now", return_value=base_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.5,
            )

        scheduler_commander.cancel_action.reset_mock()
        scheduler_commander.run_action.reset_mock()

        later_time = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        with patch.object(dt_util, "now", return_value=later_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 5, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.5,
            )

        scheduler_commander.cancel_action.assert_not_called()
        scheduler_commander.run_action.assert_not_called()
        assert schedule_use_case.get_preheating_state()[0] is True

    @pytest.mark.asyncio
    async def test_mark_preheating_complete_when_target_time_reached(
        self,
        schedule_use_case: ScheduleAnticipationActionUseCase,
    ) -> None:
        """Clear preheating state when target time is reached."""
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        scheduler_id = "schedule.heating"

        with patch.object(dt_util, "now", return_value=base_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.5,
            )

        with patch.object(dt_util, "now", return_value=target_time):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.5,
            )

        assert schedule_use_case.get_preheating_state() == (False, None, None)


class TestOvershootPrevention:
    """Test suite for overshoot risk detection."""

    @pytest.mark.asyncio
    async def test_overshoot_detected_returns_true(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Overshoot should be detected when projection exceeds threshold."""
        target_time = make_aware(datetime(2025, 1, 15, 7, 0, 0))
        current_time = make_aware(datetime(2025, 1, 15, 6, 45, 0))

        scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        overshoot_use_case.set_preheating_state(True, target_time=target_time, target_temp=21.0)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=20.8,
            current_heating_slope=3.0,
            now=current_time,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_no_overshoot_returns_false(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """No overshoot risk when projection is below threshold."""
        target_time = make_aware(datetime(2025, 1, 15, 7, 0, 0))
        current_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))

        scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        overshoot_use_case.set_preheating_state(True, target_time=target_time, target_temp=21.0)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=18.0,
            current_heating_slope=2.0,
            now=current_time,
        )

        assert result is False


class TestOvershootSkipScenarios:
    """Test overshoot skip scenarios."""

    @pytest.mark.asyncio
    async def test_skip_when_not_preheating(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Overshoot check skipped when not preheating."""
        scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=make_aware(datetime(2025, 1, 15, 7, 0, 0)),
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        overshoot_use_case.set_preheating_state(False)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=20.0,
            current_heating_slope=3.0,
            now=make_aware(datetime(2025, 1, 15, 6, 45, 0)),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_skip_when_no_timeslot(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Overshoot check skipped when no timeslot available."""
        scheduler_reader.get_next_timeslot.return_value = None

        overshoot_use_case.set_preheating_state(True)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=20.0,
            current_heating_slope=3.0,
            now=make_aware(datetime(2025, 1, 15, 6, 45, 0)),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_skip_when_slope_zero(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Overshoot check skipped when slope is zero."""
        scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=make_aware(datetime(2025, 1, 15, 7, 0, 0)),
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        overshoot_use_case.set_preheating_state(True)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=20.0,
            current_heating_slope=0.0,
            now=make_aware(datetime(2025, 1, 15, 6, 45, 0)),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_skip_when_target_time_passed(
        self,
        overshoot_use_case: CheckOvershootRiskUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Overshoot check skipped when target time has passed."""
        target_time = make_aware(datetime(2025, 1, 15, 7, 0, 0))
        scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )

        overshoot_use_case.set_preheating_state(True)

        result = await overshoot_use_case.check_overshoot_risk(
            current_temp=20.0,
            current_heating_slope=2.0,
            now=make_aware(datetime(2025, 1, 15, 7, 15, 0)),
        )

        assert result is False


class TestSchedulerDisabledBehavior:
    """Additional scheduling edge cases."""

    @pytest.mark.asyncio
    async def test_scheduler_disabled_clears_state(
        self,
        schedule_use_case: ScheduleAnticipationActionUseCase,
        scheduler_reader: Mock,
    ) -> None:
        """Clear state when scheduler becomes disabled."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        scheduler_id = "schedule.heating"

        with patch.object(dt_util, "now", return_value=now):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.9,
            )

        scheduler_reader.is_scheduler_enabled.return_value = False

        with patch.object(dt_util, "now", return_value=now):
            await schedule_use_case.schedule_action(
                anticipated_start=make_aware(datetime(2025, 1, 15, 3, 30, 0)),
                target_time=target_time,
                target_temp=21.0,
                scheduler_entity_id=scheduler_id,
                lhs=0.9,
            )

        assert schedule_use_case.get_preheating_state() == (False, None, None)
