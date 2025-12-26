"""Unit tests for HAEventBridge overshoot risk integration.

This test verifies that the overshoot risk detection is properly integrated
into the event loop and triggers during active preheating.

Related to issue: Overshoot risk detection not activating
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
import pytest

from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import HAEventBridge


def make_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC)."""
    return dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.async_create_task = Mock(side_effect=lambda coro: coro)
    hass.bus = Mock()
    hass.bus.async_fire = Mock()
    return hass


@pytest.fixture
def mock_app_service():
    """Create a mock application service."""
    app_service = Mock()
    app_service.check_overshoot_risk = AsyncMock()
    app_service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
    app_service._is_preheating_active = False
    app_service._active_scheduler_entity = None
    return app_service


@pytest.fixture
def event_bridge(mock_hass, mock_app_service):
    """Create HAEventBridge instance with mocks."""
    return HAEventBridge(
        hass=mock_hass,
        application_service=mock_app_service,
        vtherm_entity_id="climate.vtherm",
        scheduler_entity_ids=["schedule.heating"],
        monitored_entity_ids=[],
        entry_id="test_entry",
    )


class TestEventBridgeOvershootIntegration:
    """Test overshoot risk integration in event bridge."""
    
    @pytest.mark.asyncio
    async def test_overshoot_check_called_during_preheating(
        self, event_bridge, mock_app_service
    ):
        """Verify overshoot risk check is called when preheating is active."""
        # GIVEN: Preheating is active
        mock_app_service._is_preheating_active = True
        mock_app_service._active_scheduler_entity = "schedule.heating"
        
        # WHEN: Recalculate is triggered (e.g., from VTherm temperature change)
        await event_bridge._recalculate_and_publish()
        
        # THEN: Overshoot risk check should be called
        mock_app_service.check_overshoot_risk.assert_called_once_with(
            scheduler_entity_id="schedule.heating"
        )
    
    @pytest.mark.asyncio
    async def test_no_overshoot_check_when_not_preheating(
        self, event_bridge, mock_app_service
    ):
        """Verify overshoot check is NOT called when not preheating."""
        # GIVEN: Not preheating
        mock_app_service._is_preheating_active = False
        mock_app_service._active_scheduler_entity = None
        
        # WHEN: Recalculate is triggered
        await event_bridge._recalculate_and_publish()
        
        # THEN: Overshoot risk check should NOT be called
        mock_app_service.check_overshoot_risk.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_overshoot_check_before_recalculation(
        self, event_bridge, mock_app_service
    ):
        """Verify overshoot check happens BEFORE anticipation calculation."""
        # GIVEN: Preheating is active
        mock_app_service._is_preheating_active = True
        mock_app_service._active_scheduler_entity = "schedule.heating"
        
        call_order = []
        
        async def track_overshoot_call(*args, **kwargs):
            call_order.append("overshoot_check")
        
        async def track_calculation_call(*args, **kwargs):
            call_order.append("calculate_anticipation")
            return None
        
        mock_app_service.check_overshoot_risk.side_effect = track_overshoot_call
        mock_app_service.calculate_and_schedule_anticipation.side_effect = track_calculation_call
        
        # WHEN: Recalculate is triggered
        await event_bridge._recalculate_and_publish()
        
        # THEN: Overshoot check should happen BEFORE calculation
        assert call_order == ["overshoot_check", "calculate_anticipation"]
    
    @pytest.mark.asyncio
    async def test_overshoot_check_skipped_when_no_scheduler_entity(
        self, event_bridge, mock_app_service
    ):
        """Verify overshoot check is skipped if scheduler entity is not set."""
        # GIVEN: Preheating is active but no scheduler entity
        mock_app_service._is_preheating_active = True
        mock_app_service._active_scheduler_entity = None  # No scheduler entity
        
        # WHEN: Recalculate is triggered
        await event_bridge._recalculate_and_publish()
        
        # THEN: Overshoot risk check should NOT be called (missing scheduler entity)
        mock_app_service.check_overshoot_risk.assert_not_called()


class TestOvershootDetectionEndToEnd:
    """End-to-end scenario tests for overshoot detection."""
    
    @pytest.mark.asyncio
    async def test_scenario_temperature_rising_fast_triggers_overshoot(
        self, event_bridge, mock_app_service
    ):
        """Scenario: Temperature rising fast during preheating should trigger check.
        
        Timeline:
        - Preheating started at 04:00
        - Target: 21°C at 06:00
        - Current: 04:30, temp is 19°C and rising fast
        - VTherm reports temperature change
        - Event bridge should check overshoot risk
        """
        # GIVEN: Active preheating
        mock_app_service._is_preheating_active = True
        mock_app_service._active_scheduler_entity = "schedule.morning"
        
        # Mock that overshoot will be detected
        mock_app_service.check_overshoot_risk.return_value = None
        
        # WHEN: Temperature changes (simulating VTherm update)
        # This triggers _recalculate_and_publish via the event bridge
        await event_bridge._recalculate_and_publish()
        
        # THEN: Overshoot check was called
        mock_app_service.check_overshoot_risk.assert_called_once_with(
            scheduler_entity_id="schedule.morning"
        )
        
        # Note: The actual overshoot detection logic (slope calculation, 
        # estimated temp, threshold comparison) is tested in 
        # test_heating_application_service.py
