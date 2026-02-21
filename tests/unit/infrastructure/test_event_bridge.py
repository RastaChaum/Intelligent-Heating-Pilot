"""Unit tests for HAEventBridge - regression coverage for bug #81.

Bug #81: KeyError: 'anticipated_start_time' in event_bridge.py line 145
Root Cause (historical): The event bridge accessed missing keys when the
orchestrator returned a minimal payload.

Design Change:
- The bridge now always publishes a complete structure.
- Partial results are represented by the same structure with None values.

These tests ensure all response types are handled correctly:
1. None/empty dict - publish partial structure with None values
2. Partial dict (None values) - publish partial structure
3. Full data dict - publish data event with ISO timestamps
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.application import HeatingOrchestrator
from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
)

# ============================================================================
# TEST DATA & FIXTURES
# ============================================================================


@pytest.fixture
def mock_app_service() -> Mock:
    """Create mock orchestrator with default None response.

    By default, returns None (no data to publish). Individual tests override
    this return value to test different scenarios.
    """
    service = Mock(spec=HeatingOrchestrator)
    service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
    return service


@pytest.fixture
def get_ihp_enabled_mock() -> Mock:
    """Create mock get_ihp_enabled callback.

    Default: True (IHP preheating enabled).
    """
    return Mock(return_value=True)


@pytest.fixture
def event_bridge(
    hass: HomeAssistant,
    mock_app_service: Mock,
    get_ihp_enabled_mock: Mock,
) -> HAEventBridge:
    """Create HAEventBridge instance for testing.

    Configured with a bedroom climate entity and scheduler switch.
    """
    bridge = HAEventBridge(
        hass=hass,
        orchestrator=mock_app_service,
        vtherm_entity_id="climate.bedroom",
        scheduler_entity_ids=["switch.bedroom_schedule"],
        monitored_entity_ids=["sensor.bedroom_humidity", "sensor.cloud_coverage"],
        entry_id="test_entry",
        get_ihp_enabled_func=get_ihp_enabled_mock,
    )
    return bridge


def create_full_anticipation_data(
    anticipated_start_time: datetime | None = None,
    next_schedule_time: datetime | None = None,
) -> dict:
    """Create a complete anticipation data dict (successful case).

    Args:
        anticipated_start_time: When should preheating start
        next_schedule_time: When is the next scheduled event

    Returns:
        Full data dict as returned by calculate_and_schedule_anticipation()
    """
    now = datetime.now(timezone.utc)
    return {
        "anticipated_start_time": anticipated_start_time or now + timedelta(minutes=30),
        "next_schedule_time": next_schedule_time or now + timedelta(hours=1),
        "next_target_temperature": 21.0,
        "anticipation_minutes": 30.0,
        "current_temp": 18.5,
        "learned_heating_slope": 2.5,
        "confidence_level": 85.0,
        "scheduler_entity": "switch.bedroom_schedule",
    }


def create_partial_anticipation_data(
    current_temp: float | None = 18.5,
    learned_heating_slope: float | None = 2.5,
) -> dict:
    """Create a partial anticipation data dict (minimal values).

    Used when no scheduler is configured or no timeslot is available.

    Returns:
        Partial data dict with None fields for scheduling-related values
    """
    return {
        "anticipated_start_time": None,
        "next_schedule_time": None,
        "next_target_temperature": None,
        "anticipation_minutes": None,
        "current_temp": current_temp,
        "learned_heating_slope": learned_heating_slope,
        "confidence_level": None,
        "scheduler_entity": None,
    }


# ============================================================================
# TEST CLASS: Clear Values Signal (Bug Reproducer)
# ============================================================================


class TestPartialDataPublishing:
    """Regression tests for bug #81: partial data handling.

    These tests ensure partial payloads do not trigger KeyError and the
    published event always contains the complete structure with None values.
    """

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_publishes_partial_event_when_no_scheduler_configured(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that partial data publishes a complete structure.

        Regression test for bug #81: When IHP has no scheduler,
        calculate_and_schedule_anticipation() returns a partial payload.
        The event bridge must publish a full structure with None values,
        NOT attempt to access missing keys.
        """
        # GIVEN: App service returns partial data
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Scheduler state changes (triggering recalculation)
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial event published without KeyError
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_type, event_data = call_args[0], call_args[1]

        assert event_type == "intelligent_heating_pilot_anticipation_calculated"
        assert event_data["entry_id"] == "test_entry"
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert event_data["next_target_temperature"] is None
        assert event_data["anticipation_minutes"] is None
        assert event_data["current_temp"] == 18.5
        assert event_data["learned_heating_slope"] == 2.5
        assert event_data["confidence_level"] is None
        assert event_data["scheduler_entity"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_partial_data_does_not_access_missing_keys(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Verify partial data handler keeps all keys and values nullable."""
        # GIVEN: partial data returned
        partial_data = create_partial_anticipation_data()
        mock_app_service.calculate_and_schedule_anticipation.return_value = partial_data
        event_bridge.setup_listeners()

        # WHEN: Recalculation triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Event published with full structure (no KeyError)
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]

        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_multiple_partial_signals_handled_sequentially(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Verify multiple partial responses publish consistently."""
        # GIVEN: App service returns partial data
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Multiple scheduler events trigger recalculations
        for i in range(3):
            hass.states.async_set("switch.bedroom_schedule", "on" if i % 2 == 0 else "off")
            await hass.async_block_till_done()

        # THEN: Three partial events published without error
        assert mock_async_fire.call_count == 3
        for call in mock_async_fire.call_args_list:
            event_data = call[0][1]
            assert event_data["anticipated_start_time"] is None
            assert event_data["next_schedule_time"] is None
            assert "clear_values" not in event_data


class TestFullDataPublishing:
    """Test publishing of complete anticipation data (successful forecast case)."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_publishes_anticipation_event_with_full_data(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test publishing when app service returns complete anticipation dict.

        This is the success case where a valid timeslot and forecast exist.
        All data fields should be published without error.
        """
        # GIVEN: Full anticipation data
        full_data = create_full_anticipation_data()
        mock_app_service.calculate_and_schedule_anticipation.return_value = full_data
        event_bridge.setup_listeners()

        # WHEN: Scheduler state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Full anticipation event published
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_type, event_data = call_args[0], call_args[1]

        assert event_type == "intelligent_heating_pilot_anticipation_calculated"
        assert event_data["entry_id"] == "test_entry"
        assert (
            event_data["anticipated_start_time"] == full_data["anticipated_start_time"].isoformat()
        )
        assert event_data["next_schedule_time"] == full_data["next_schedule_time"].isoformat()
        assert event_data["next_target_temperature"] == 21.0
        assert event_data["anticipation_minutes"] == 30.0
        assert event_data["current_temp"] == 18.5
        assert event_data["learned_heating_slope"] == 2.5
        assert event_data["confidence_level"] == 85.0
        assert event_data["scheduler_entity"] == "switch.bedroom_schedule"
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_all_data_fields_published_correctly(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Verify all datetime fields are converted to ISO format strings."""
        # GIVEN: Full anticipation data with specific times
        start_time = datetime(2026, 2, 8, 14, 30, 0, tzinfo=timezone.utc)
        schedule_time = datetime(2026, 2, 8, 15, 0, 0, tzinfo=timezone.utc)
        full_data = create_full_anticipation_data(
            anticipated_start_time=start_time,
            next_schedule_time=schedule_time,
        )
        mock_app_service.calculate_and_schedule_anticipation.return_value = full_data
        event_bridge.setup_listeners()

        # WHEN: Recalculation triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Times converted to ISO format strings
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]

        assert event_data["anticipated_start_time"] == start_time.isoformat()
        assert event_data["next_schedule_time"] == schedule_time.isoformat()

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_scheduler_entity_optional_field_handled(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that optional scheduler_entity field has default value."""
        # GIVEN: Data without scheduler_entity
        full_data = create_full_anticipation_data()
        del full_data["scheduler_entity"]  # Remove optional field
        mock_app_service.calculate_and_schedule_anticipation.return_value = full_data
        event_bridge.setup_listeners()

        # WHEN: Recalculation triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Scheduler entity defaults to None
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]

        assert event_data["scheduler_entity"] is None


# ============================================================================
# TEST CLASS: None Response
# ============================================================================


class TestNoneResponse:
    """Test handling when app service returns None (no data to publish)."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_skips_publishing_when_no_anticipation_data(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that None response results in partial structure."""
        # GIVEN: App service returns None
        mock_app_service.calculate_and_schedule_anticipation.return_value = None
        event_bridge.setup_listeners()

        # WHEN: Scheduler state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial structure published (fallback)
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_type, event_data = call_args[0], call_args[1]

        assert event_type == "intelligent_heating_pilot_anticipation_calculated"
        assert event_data["entry_id"] == "test_entry"
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert event_data["next_target_temperature"] is None
        assert event_data["anticipation_minutes"] is None
        assert event_data["current_temp"] is None
        assert event_data["learned_heating_slope"] is None
        assert event_data["confidence_level"] is None
        assert event_data["scheduler_entity"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_none_response_never_accesses_data_keys(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Verify None response doesn't attempt to access any keys."""
        # GIVEN: None response from app service
        mock_app_service.calculate_and_schedule_anticipation.return_value = None
        event_bridge.setup_listeners()

        # WHEN: Recalculation triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial structure published with all keys present
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert len(event_data) == 9
        assert event_data["entry_id"] == "test_entry"
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert event_data["next_target_temperature"] is None
        assert event_data["anticipation_minutes"] is None
        assert event_data["current_temp"] is None
        assert event_data["learned_heating_slope"] is None
        assert event_data["confidence_level"] is None
        assert event_data["scheduler_entity"] is None


# ============================================================================
# TEST CLASS: IHP Enabled/Disabled Parameter
# ============================================================================


class TestIHPEnabledParameter:
    """Test that ihp_enabled parameter is correctly passed to app service."""

    @pytest.mark.asyncio
    async def test_passes_ihp_disabled_to_app_service(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify ihp_enabled=False is passed when IHP is disabled.

        Related to bug #81 - without proper ihp_enabled handling,
        preheating could restart when disabled.
        """
        # GIVEN: IHP disabled
        get_ihp_enabled_mock.return_value = False
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Scheduler state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=False passed to app service
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_passes_ihp_enabled_to_app_service(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify ihp_enabled=True is passed when IHP is enabled."""
        # GIVEN: IHP enabled
        get_ihp_enabled_mock.return_value = True
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_full_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Scheduler state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=True passed to app service
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_ihp_enabled_parameter_used_with_partial_data(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify ihp_enabled parameter combined with partial response."""
        # GIVEN: IHP disabled and partial response
        get_ihp_enabled_mock.return_value = False
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Event triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: ihp_enabled parameter passed and partial event published
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data


# ============================================================================
# TEST CLASS: Multiple Event Triggers
# ============================================================================


class TestMultipleEventTriggers:
    """Test handling multiple rapid consecutive events."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_handles_rapid_consecutive_partial_events(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that rapid partial responses don't cause race conditions."""
        # GIVEN: partial response configured
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Two scheduler entities trigger events rapidly
        hass.states.async_set("switch.bedroom_schedule", "on")
        hass.states.async_set("sensor.cloud_coverage", "30")
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()

        # THEN: Each triggers correct partial event (no KeyError)
        assert mock_async_fire.call_count == 3
        for call in mock_async_fire.call_args_list:
            event_data = call[0][1]
            assert event_data["anticipated_start_time"] is None
            assert event_data["next_schedule_time"] is None
            assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_handles_alternating_clear_and_data_events(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test switching between partial and full data responses.

        Simulates scheduler being enabled/disabled, causing alternating
        responses from app service.
        """
        event_bridge.setup_listeners()

        # WHEN: First event - partial response
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial event published
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data

        mock_async_fire.reset_mock()

        # WHEN: Second event - full data response
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_full_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()

        # THEN: Data event published
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert "clear_values" not in event_data
        assert "anticipated_start_time" in event_data

        mock_async_fire.reset_mock()

        # WHEN: Third event - None response
        mock_app_service.calculate_and_schedule_anticipation.return_value = None
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial event published (fallback for None)
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_vtherm_temperature_change_with_partial_data(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test VTherm temperature changes with partial response."""
        # GIVEN: VTherm at initial state, partial response
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 18.5},
        )
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: VTherm temperature changes (slope update)
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 19.0},
        )
        await hass.async_block_till_done()

        # THEN: Partial event published without error
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_monitored_entity_changes_with_all_response_types(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test monitored entities (humidity, cloud cover) with all response types."""
        event_bridge.setup_listeners()

        # Test humidity change with partial response
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        hass.states.async_set("sensor.bedroom_humidity", "45")
        await hass.async_block_till_done()

        call_args = mock_async_fire.call_args[0]
        assert call_args[1]["anticipated_start_time"] is None
        assert call_args[1]["next_schedule_time"] is None
        assert "clear_values" not in call_args[1]

        mock_async_fire.reset_mock()

        # Test cloud cover change with full data
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_full_anticipation_data()
        )
        hass.states.async_set("sensor.cloud_coverage", "25")
        await hass.async_block_till_done()

        call_args = mock_async_fire.call_args[0]
        assert "anticipated_start_time" in call_args[1]


# ============================================================================
# TEST CLASS: Edge Cases & Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_empty_dict_response_treated_as_falsy(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that empty dict {} yields partial structure."""
        # GIVEN: Empty dict response (technically falsy but not None)
        mock_app_service.calculate_and_schedule_anticipation.return_value = {}
        event_bridge.setup_listeners()

        # WHEN: Event triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Partial event published (falsy behavior)
        mock_async_fire.assert_called_once()
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_partial_data_has_no_clear_values_flag(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Test that partial data does not include a clear_values flag."""
        # GIVEN: Partial response
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        # WHEN: Event triggered
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Event published without clear_values
        call_args = mock_async_fire.call_args[0]
        event_data = call_args[1]
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_entry_id_consistency_across_response_types(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
    ) -> None:
        """Verify entry_id is always included in published events.

        Entry ID should be present regardless of response type.
        """
        event_bridge.setup_listeners()

        # Test with partial data
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_partial_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        call_args = mock_async_fire.call_args[0]
        assert call_args[1]["entry_id"] == "test_entry"

        mock_async_fire.reset_mock()

        # Test with full data
        mock_app_service.calculate_and_schedule_anticipation.return_value = (
            create_full_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()

        call_args = mock_async_fire.call_args[0]
        assert call_args[1]["entry_id"] == "test_entry"

        mock_async_fire.reset_mock()

        # Test with None
        mock_app_service.calculate_and_schedule_anticipation.return_value = None
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        call_args = mock_async_fire.call_args[0]
        assert call_args[1]["entry_id"] == "test_entry"
