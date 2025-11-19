"""Unit tests for HeatingApplicationService revert logic.

Tests the fix for issue #16: Pre-heating mechanism fails to revert to 
scheduled state when conditions change (anticipated start time moves later).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
import pytest

from custom_components.intelligent_heating_pilot.application import HeatingApplicationService
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduleTimeslot,
    EnvironmentState,
)


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def mock_adapters():
    """Create mock adapters for testing."""
    scheduler_reader = Mock()
    scheduler_reader.get_next_timeslot = AsyncMock()
    
    model_storage = Mock()
    model_storage.get_learned_heating_slope = AsyncMock(return_value=2.0)
    model_storage.get_all_slope_data = AsyncMock(return_value=[])
    
    scheduler_commander = Mock()
    scheduler_commander.run_action = AsyncMock()
    scheduler_commander.cancel_action = AsyncMock()
    
    climate_commander = Mock()
    climate_commander.turn_on_heat = AsyncMock()
    climate_commander.turn_off = AsyncMock()
    
    environment_reader = Mock()
    environment_reader.get_current_environment = AsyncMock()
    environment_reader.is_heating_active = Mock(return_value=False)
    environment_reader.get_vtherm_slope = Mock(return_value=None)
    
    return {
        "scheduler_reader": scheduler_reader,
        "model_storage": model_storage,
        "scheduler_commander": scheduler_commander,
        "climate_commander": climate_commander,
        "environment_reader": environment_reader,
    }


@pytest.fixture
def app_service(mock_adapters):
    """Create HeatingApplicationService with mocked adapters."""
    return HeatingApplicationService(
        scheduler_reader=mock_adapters["scheduler_reader"],
        model_storage=mock_adapters["model_storage"],
        scheduler_commander=mock_adapters["scheduler_commander"],
        climate_commander=mock_adapters["climate_commander"],
        environment_reader=mock_adapters["environment_reader"],
        lhs_window_hours=6.0,
    )


class TestRevertLogicWhenAnticipatedStartMoves:
    """Test suite for issue #16: Revert when anticipated start time changes."""
    
    @pytest.mark.asyncio
    async def test_revert_when_anticipated_start_moves_later(
        self, app_service, mock_adapters
    ):
        """Test that system reverts to current schedule when anticipated start moves later.
        
        Scenario from issue #16:
        1. Pre-heating starts at 04:00 with LHS=2°C/h
        2. During heating, LHS improves to 4°C/h
        3. Anticipated start recalculates to 05:00 (later than now=04:45)
        4. System should revert to current scheduled temperature
        """
        # Setup: Schedule at 06:30, target temp 21°C
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))  # 04:00
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))  # 06:30
        
        timeslot = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )
        
        environment = EnvironmentState(
            current_temp=19.0,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=base_time,
        )
        
        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment
        mock_adapters["model_storage"].get_learned_heating_slope.return_value = 2.0
        
        # Step 1: Initial calculation triggers pre-heating at 04:00
        # Mock dt_util.now() to return base_time
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=base_time):
            # LHS=2°C/h → anticipated start = 04:00 (in past, so trigger now)
            await app_service.calculate_and_schedule_anticipation()
        
        # Verify pre-heating was triggered
        mock_adapters["scheduler_commander"].run_action.assert_called_once_with(target_time)
        assert app_service._is_preheating_active is True
        assert app_service._preheating_target_time == target_time
        
        # Step 2: Time advances to 04:45, LHS improves to 4°C/h
        later_time = make_aware(datetime(2025, 1, 15, 4, 45, 0))  # 04:45
        environment_later = EnvironmentState(
            current_temp=20.0,  # Heated up
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=later_time,
        )
        
        mock_adapters["environment_reader"].get_current_environment.return_value = environment_later
        mock_adapters["model_storage"].get_learned_heating_slope.return_value = 4.0
        mock_adapters["scheduler_commander"].run_action.reset_mock()
        
        # Step 3: Recalculate - anticipated start now 05:00 (later than 04:45)
        # With better LHS, needs less time → should STOP heating
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=later_time):
            await app_service.calculate_and_schedule_anticipation()
        
        # Verify system reverted to current schedule
        mock_adapters["scheduler_commander"].cancel_action.assert_called_once()
        assert app_service._is_preheating_active is False
        assert app_service._preheating_target_time is None
        
        # Verify we did NOT trigger another run_action (that would restart heating)
        mock_adapters["scheduler_commander"].run_action.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_continue_heating_when_still_needed(
        self, app_service, mock_adapters
    ):
        """Test that system continues heating when anticipated start is still in past."""
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        
        timeslot = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )
        
        environment = EnvironmentState(
            current_temp=19.0,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=base_time,
        )
        
        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment
        mock_adapters["model_storage"].get_learned_heating_slope.return_value = 1.5
        
        # Initial calculation - low LHS means early start
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=base_time):
            await app_service.calculate_and_schedule_anticipation()
        
        assert app_service._is_preheating_active is True
        
        # Time advances but LHS stays low - still need heating
        later_time = make_aware(datetime(2025, 1, 15, 4, 30, 0))
        environment_later = EnvironmentState(
            current_temp=19.5,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=later_time,
        )
        
        mock_adapters["environment_reader"].get_current_environment.return_value = environment_later
        mock_adapters["scheduler_commander"].cancel_action.reset_mock()
        
        # Recalculate - should continue heating
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=later_time):
            await app_service.calculate_and_schedule_anticipation()
        
        # Should NOT revert (cancel not called)
        mock_adapters["scheduler_commander"].cancel_action.assert_not_called()
        assert app_service._is_preheating_active is True
    
    @pytest.mark.asyncio
    async def test_mark_preheating_complete_when_target_time_reached(
        self, app_service, mock_adapters
    ):
        """Test that pre-heating state is cleared when target time is reached."""
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        
        timeslot = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )
        
        environment = EnvironmentState(
            current_temp=19.0,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=base_time,
        )
        
        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment
        mock_adapters["model_storage"].get_learned_heating_slope.return_value = 2.0
        
        # Start pre-heating
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=base_time):
            await app_service.calculate_and_schedule_anticipation()
        assert app_service._is_preheating_active is True
        
        # Time reaches target
        environment_at_target = EnvironmentState(
            current_temp=21.0,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=target_time,  # Reached target time
        )
        
        mock_adapters["environment_reader"].get_current_environment.return_value = environment_at_target
        
        # Recalculate at target time
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=target_time):
            await app_service.calculate_and_schedule_anticipation()
        
        # Pre-heating should be marked complete
        assert app_service._is_preheating_active is False
        assert app_service._preheating_target_time is None


class TestOvershootPrevention:
    """Test suite for overshoot prevention using scheduler."""
    
    @pytest.mark.asyncio
    async def test_overshoot_uses_scheduler_cancel_not_direct_turnoff(
        self, app_service, mock_adapters
    ):
        """Test that overshoot prevention uses scheduler.cancel_action() instead of climate.turn_off().
        
        This is the fix for issue #16 part 2: Use scheduler instead of direct VTherm control.
        """
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        current_time = make_aware(datetime(2025, 1, 15, 6, 0, 0))
        
        timeslot = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )
        
        environment = EnvironmentState(
            current_temp=20.0,  # Already close to target
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=current_time,
        )
        
        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment
        mock_adapters["environment_reader"].get_vtherm_slope.return_value = 3.0  # High heating rate
        
        # Mark as pre-heating active
        app_service._is_preheating_active = True
        app_service._preheating_target_time = target_time
        
        # Check overshoot - will detect overshoot risk
        # (current 20°C + 3°C/h * 0.5h = 21.5°C > threshold 21.5°C)
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=current_time):
            await app_service.check_overshoot_risk()
        
        # Should use scheduler cancel_action, NOT climate turn_off
        mock_adapters["scheduler_commander"].cancel_action.assert_called_once()
        mock_adapters["climate_commander"].turn_off.assert_not_called()
        
        # Pre-heating state should be cleared
        assert app_service._is_preheating_active is False
        assert app_service._preheating_target_time is None


class TestNoDirectVThermControl:
    """Test suite ensuring scheduler is used instead of direct VTherm control."""
    
    @pytest.mark.asyncio
    async def test_preheating_start_uses_only_scheduler(
        self, app_service, mock_adapters
    ):
        """Test that starting pre-heating uses ONLY scheduler.run_action(), no direct VTherm control.
        
        This verifies the fix for issue #16: Remove direct climate_commander calls.
        """
        base_time = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        
        timeslot = ScheduleTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="morning",
            scheduler_entity="schedule.heating",
        )
        
        environment = EnvironmentState(
            current_temp=19.0,
            outdoor_temp=5.0,
            humidity=60.0,
            cloud_coverage=50.0,
            timestamp=base_time,
        )
        
        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment
        mock_adapters["model_storage"].get_learned_heating_slope.return_value = 2.0
        
        # Calculate and schedule - should trigger pre-heating
        with patch("custom_components.intelligent_heating_pilot.application.dt_util.now", return_value=base_time):
            await app_service.calculate_and_schedule_anticipation()
        
        # Verify scheduler.run_action was called
        mock_adapters["scheduler_commander"].run_action.assert_called_once_with(target_time)
        
        # Verify climate_commander was NOT used directly
        mock_adapters["climate_commander"].turn_on_heat.assert_not_called()
        mock_adapters["climate_commander"].set_temperature.assert_not_called()
        mock_adapters["climate_commander"].set_hvac_mode.assert_not_called()
