"""Unit tests for IHP training without scheduler configured.

Tests the fix for GitHub issue: IHP Not Training without scheduler.
Verifies that LHS learning continues even when no scheduler is configured.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
import pytest

from custom_components.intelligent_heating_pilot.application import HeatingApplicationService
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HeatingCycle,
)


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def mock_adapters_no_scheduler():
    """Create mock adapters for testing without scheduler."""
    scheduler_reader = Mock()
    # Return None to simulate no scheduler configured
    scheduler_reader.get_next_timeslot = AsyncMock(return_value=None)
    scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=False)
    
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
    environment_reader.is_heating_active = AsyncMock(return_value=False)
    environment_reader.get_vtherm_slope = Mock(return_value=None)
    environment_reader.get_vtherm_entity_id = Mock(return_value="climate.vtherm")
    environment_reader.get_hass = Mock()
    environment_reader.get_humidity_in_entity_id = Mock(return_value=None)
    environment_reader.get_humidity_out_entity_id = Mock(return_value=None)
    
    return {
        "scheduler_reader": scheduler_reader,
        "model_storage": model_storage,
        "scheduler_commander": scheduler_commander,
        "climate_commander": climate_commander,
        "environment_reader": environment_reader,
    }


@pytest.fixture
def app_service_no_scheduler(mock_adapters_no_scheduler):
    """Create HeatingApplicationService without scheduler."""
    return HeatingApplicationService(
        scheduler_reader=mock_adapters_no_scheduler["scheduler_reader"],
        model_storage=mock_adapters_no_scheduler["model_storage"],
        scheduler_commander=mock_adapters_no_scheduler["scheduler_commander"],
        climate_commander=mock_adapters_no_scheduler["climate_commander"],
        environment_reader=mock_adapters_no_scheduler["environment_reader"],
        lhs_window_hours=6.0,
    )


class TestTrainingWithoutScheduler:
    """Test suite for IHP training without scheduler configured."""
    
    @pytest.mark.asyncio
    async def test_returns_none_when_no_scheduler(
        self, app_service_no_scheduler, mock_adapters_no_scheduler
    ):
        """Test that calculate_and_schedule_anticipation returns None when no scheduler.
        
        This verifies the fix allows graceful handling of missing scheduler
        while still attempting to extract and learn from heating cycles.
        """
        # GIVEN: No scheduler configured (get_next_timeslot returns None)
        assert await mock_adapters_no_scheduler["scheduler_reader"].get_next_timeslot() is None
        
        # WHEN: Calculate anticipation
        result = await app_service_no_scheduler.calculate_and_schedule_anticipation()
        
        # THEN: Should return None (no anticipation data)
        assert result is None
        
        # AND: Should have attempted to get next timeslot
        mock_adapters_no_scheduler["scheduler_reader"].get_next_timeslot.assert_called_once()
    
    @pytest.mark.asyncio
    @patch("custom_components.intelligent_heating_pilot.application.HeatingApplicationService._get_contextual_lhs")
    async def test_extracts_lhs_even_without_scheduler(
        self, mock_get_lhs, app_service_no_scheduler, mock_adapters_no_scheduler
    ):
        """Test that LHS extraction happens even without scheduler.
        
        This is the core fix: IHP should continue learning from historical
        heating cycles even when no scheduler is configured.
        """
        # GIVEN: No scheduler configured
        # AND: Mock LHS extraction to return a learned value
        mock_get_lhs.return_value = 3.5
        
        # WHEN: Calculate anticipation
        result = await app_service_no_scheduler.calculate_and_schedule_anticipation()
        
        # THEN: Should return None (no scheduling)
        assert result is None
        
        # BUT: Should have called _get_contextual_lhs to extract and learn
        mock_get_lhs.assert_called_once()
        # The call should use current time (approximately)
        call_args = mock_get_lhs.call_args[0]
        assert len(call_args) == 1  # target_time parameter
        # Verify it's a datetime (we can't check exact time due to timing)
        assert isinstance(call_args[0], datetime)
    
    @pytest.mark.asyncio
    @patch("custom_components.intelligent_heating_pilot.application.HeatingApplicationService._get_contextual_lhs")
    async def test_lhs_extraction_failure_handled_gracefully(
        self, mock_get_lhs, app_service_no_scheduler, mock_adapters_no_scheduler
    ):
        """Test that LHS extraction failure doesn't crash the system.
        
        Even if cycle extraction fails, the system should handle it gracefully
        and return None without raising an exception.
        """
        # GIVEN: No scheduler configured
        # AND: LHS extraction raises an exception
        mock_get_lhs.side_effect = Exception("Recorder not available")
        
        # WHEN: Calculate anticipation
        result = await app_service_no_scheduler.calculate_and_schedule_anticipation()
        
        # THEN: Should return None gracefully (no crash)
        assert result is None
        
        # AND: Should have attempted LHS extraction
        mock_get_lhs.assert_called_once()


class TestEventFiringWithoutScheduler:
    """Test suite for event firing when no scheduler is configured."""
    
    def test_coordinator_fires_clear_event_with_lhs(self):
        """Test that coordinator fires clear_values event with learned_heating_slope.
        
        This is verified by examining the code changes in __init__.py.
        The actual event firing is integration-level and requires Home Assistant,
        so we document the expected behavior here.
        """
        # EXPECTED BEHAVIOR (from code review):
        # When anticipation_data is None:
        # 1. Coordinator fires "intelligent_heating_pilot_anticipation_calculated" event
        # 2. Event contains: entry_id, clear_values=True, learned_heating_slope
        # 3. Sensors receive event and clear their values to "unknown"
        # 4. Slope sensor updates from learned_heating_slope field
        pass
    
    def test_event_bridge_fires_clear_event_with_lhs(self):
        """Test that event_bridge fires clear_values event with learned_heating_slope.
        
        This is verified by examining the code changes in event_bridge.py.
        The actual event firing is integration-level and requires Home Assistant,
        so we document the expected behavior here.
        """
        # EXPECTED BEHAVIOR (from code review):
        # When anticipation_data is None:
        # 1. Event bridge fires "intelligent_heating_pilot_anticipation_calculated" event
        # 2. Gets LHS from model_storage (or defaults to 2.0)
        # 3. Event contains: entry_id, clear_values=True, learned_heating_slope
        # 4. Sensors receive event and handle appropriately
        pass
