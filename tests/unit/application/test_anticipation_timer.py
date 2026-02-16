"""Unit tests for anticipation timer mechanism.

Tests the timer-based anticipation triggering mechanism that ensures
IHP triggers climate control at the anticipated start time, independent
of climate entity state changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.application import HeatingApplicationService
from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    PredictionResult,
    ScheduledTimeslot,
)


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.async_create_task = Mock()
    # Mock the event loop to support async_track_point_in_time
    hass.loop = Mock()
    hass.loop.time = Mock(return_value=0.0)
    hass.loop.call_at = Mock(return_value=Mock())  # Returns cancel callback
    return hass


@pytest.fixture
def mock_adapters(mock_hass):
    """Create mock adapters for testing."""
    scheduler_reader = Mock()
    scheduler_reader.get_next_timeslot = AsyncMock()
    scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

    model_storage = Mock()
    model_storage.get_learned_heating_slope = AsyncMock(return_value=2.0)
    model_storage.get_all_slope_data = AsyncMock(return_value=[])
    model_storage.get_cached_global_lhs = AsyncMock(return_value=None)
    model_storage.set_cached_global_lhs = AsyncMock()
    model_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
    model_storage.set_cached_contextual_lhs = AsyncMock()

    scheduler_commander = Mock()
    scheduler_commander.run_action = AsyncMock()
    scheduler_commander.cancel_action = AsyncMock()

    climate_commander = Mock()
    climate_commander.turn_on_heat = AsyncMock()
    climate_commander.turn_off = AsyncMock()
    climate_commander.set_temperature = AsyncMock()
    climate_commander.set_hvac_mode = AsyncMock()

    environment_reader = Mock()
    environment_reader.get_current_environment = AsyncMock()

    # Climate data reader (replaces old vtherm_metadata/slope/state readers)
    climate_data_reader = Mock()
    climate_data_reader.get_vtherm_entity_id = Mock(return_value="climate.test_vtherm")
    climate_data_reader.get_current_slope = Mock(return_value=None)
    climate_data_reader.is_heating_active = Mock(return_value=False)

    # Context reader (provides HA context for adapters)
    environment_context_reader = Mock()
    environment_context_reader.get_hass = Mock(return_value=mock_hass)
    environment_context_reader.get_humidity_in_entity_id = Mock(return_value=None)
    environment_context_reader.get_humidity_out_entity_id = Mock(return_value=None)
    environment_context_reader.get_outdoor_temp_entity_id = Mock(return_value=None)
    environment_context_reader.get_cloud_cover_entity_id = Mock(return_value=None)

    # Mock timer scheduler
    timer_scheduler = Mock()
    timer_scheduler.schedule_timer = Mock(return_value=Mock())  # Returns cancel function

    # Mock lifecycle managers
    heating_cycle_manager = AsyncMock(spec=HeatingCycleLifecycleManager)
    heating_cycle_manager.get_cycles_for_target_time = AsyncMock(return_value=[])
    heating_cycle_manager.get_cycles_for_window = AsyncMock(return_value=[])

    lhs_manager = AsyncMock(spec=LhsLifecycleManager)
    lhs_manager.get_contextual_lhs = AsyncMock(return_value=2.5)
    lhs_manager.get_global_lhs = AsyncMock(return_value=2.5)
    lhs_manager.update_global_lhs_from_cycles = AsyncMock(return_value=2.5)
    lhs_manager.update_contextual_lhs_from_cycles = AsyncMock(return_value={0: 2.0, 12: 3.0})

    return {
        "scheduler_reader": scheduler_reader,
        "model_storage": model_storage,
        "scheduler_commander": scheduler_commander,
        "climate_commander": climate_commander,
        "environment_reader": environment_reader,
        "climate_data_reader": climate_data_reader,
        "environment_context_reader": environment_context_reader,
        "hass": mock_hass,
        "timer_scheduler": timer_scheduler,
        "heating_cycle_lifecycle_manager": heating_cycle_manager,
        "lhs_lifecycle_manager": lhs_manager,
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
        climate_data_reader=mock_adapters["climate_data_reader"],
        environment_context_reader=mock_adapters["environment_context_reader"],
        timer_scheduler=mock_adapters["timer_scheduler"],
        heating_cycle_lifecycle_manager=mock_adapters["heating_cycle_lifecycle_manager"],
        lhs_lifecycle_manager=mock_adapters["lhs_lifecycle_manager"],
        lhs_window_hours=6.0,
    )


class TestAnticipationTimer:
    """Test suite for timer-based anticipation mechanism."""

    @pytest.mark.asyncio
    async def test_timer_scheduled_for_future_anticipation(self, app_service, mock_adapters):
        """Test that a timer is scheduled when anticipated start is in the future."""
        # Setup: Current time is 04:00, anticipated start is 06:00, target is 07:30
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        timeslot = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_slot",
            scheduler_entity="switch.test_scheduler",
        )

        environment = EnvironmentState(
            now,
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
        )

        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment

        # Execute with mocked time
        with patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()

        # Verify: Timer should be scheduled (anticipation_timer_cancel should be set)
        assert app_service._anticipation_timer_cancel is not None
        assert app_service._active_scheduler_entity == "switch.test_scheduler"

        # Verify: Action should NOT be triggered immediately
        mock_adapters["scheduler_commander"].run_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_timer_rescheduled_when_anticipated_start_updates(
        self, app_service, mock_adapters
    ):
        """Test timer reschedules when anticipated start time changes."""
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        timeslot = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_slot",
            scheduler_entity="switch.test_scheduler",
        )

        environment = EnvironmentState(
            now,
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
        )

        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment

        first_prediction = PredictionResult(
            anticipated_start_time=make_aware(datetime(2025, 1, 15, 5, 0, 0)),
            estimated_duration_minutes=90.0,
            confidence_level=0.9,
            learned_heating_slope=1.5,
        )
        second_prediction = PredictionResult(
            anticipated_start_time=make_aware(datetime(2025, 1, 15, 4, 30, 0)),
            estimated_duration_minutes=120.0,
            confidence_level=0.85,
            learned_heating_slope=1.6,
        )

        cancel_first = Mock()
        cancel_second = Mock()

        with patch.object(
            app_service._prediction_service,
            "predict_heating_time",
            side_effect=[first_prediction, second_prediction],
        ) as predict_mock, patch.object(
            app_service._timer_scheduler,
            "schedule_timer",
            side_effect=[cancel_first, cancel_second],
        ) as schedule_mock, patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()
            await app_service.calculate_and_schedule_anticipation()

        assert predict_mock.call_count == 2
        assert schedule_mock.call_count == 2
        assert schedule_mock.call_args_list[0].args[0] == first_prediction.anticipated_start_time
        assert schedule_mock.call_args_list[1].args[0] == second_prediction.anticipated_start_time
        assert cancel_first.called
        assert not cancel_second.called
        assert app_service._anticipation_timer_cancel is cancel_second

    @pytest.mark.asyncio
    async def test_immediate_trigger_when_anticipation_in_past(self, app_service, mock_adapters):
        """Test that action is triggered immediately when anticipated start is in the past."""
        # Setup: Current time is 06:30, anticipated start was 06:00, target is 07:30
        now = make_aware(datetime(2025, 1, 15, 6, 30, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        timeslot = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_slot",
            scheduler_entity="switch.test_scheduler",
        )

        environment = EnvironmentState(
            now,
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
        )

        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment

        # Execute with mocked time
        with patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()

        # Verify: Action should be triggered immediately
        mock_adapters["scheduler_commander"].run_action.assert_called_once_with(
            target_time, "switch.test_scheduler"
        )

        # Verify: Pre-heating should be marked as active
        assert app_service._is_preheating_active is True
        assert app_service._preheating_target_time == target_time

    @pytest.mark.asyncio
    async def test_timer_cancelled_when_anticipation_state_cleared(
        self, app_service, mock_adapters
    ):
        """Test that timer is cancelled when anticipation state is cleared."""
        # Setup: Schedule a timer first
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        timeslot = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_slot",
            scheduler_entity="switch.test_scheduler",
        )

        environment = EnvironmentState(
            now,
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
        )

        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment

        # Schedule timer
        with patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()

        # Verify timer is set
        assert app_service._anticipation_timer_cancel is not None

        # Clear anticipation state
        await app_service._clear_anticipation_state()

        # Verify timer was cancelled
        assert app_service._anticipation_timer_cancel is None
        # Note: We can't directly verify the callback was called without more complex mocking
        # but we verified it was reset to None

    @pytest.mark.asyncio
    async def test_timer_cancelled_when_scheduler_disabled(self, app_service, mock_adapters):
        """Test that timer is cancelled when scheduler is disabled."""
        # Setup: Schedule a timer first
        now = make_aware(datetime(2025, 1, 15, 4, 0, 0))
        target_time = make_aware(datetime(2025, 1, 15, 7, 30, 0))

        timeslot = ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="test_slot",
            scheduler_entity="switch.test_scheduler",
        )

        environment = EnvironmentState(
            now,
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
        )

        mock_adapters["scheduler_reader"].get_next_timeslot.return_value = timeslot
        mock_adapters["environment_reader"].get_current_environment.return_value = environment

        # Schedule timer
        with patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()

        # Verify timer is set
        assert app_service._anticipation_timer_cancel is not None

        # Now simulate scheduler being disabled
        mock_adapters["scheduler_reader"].is_scheduler_enabled.return_value = False

        # Call calculate_and_schedule_anticipation again
        with patch.object(dt_util, "now", return_value=now):
            await app_service.calculate_and_schedule_anticipation()

        # Verify timer was cancelled (state cleared)
        assert app_service._anticipation_timer_cancel is None
        assert app_service._active_scheduler_entity is None
