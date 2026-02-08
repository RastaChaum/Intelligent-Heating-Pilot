"""Unit tests for HAEventBridge respecting ihp_enabled state.

This test suite verifies that the HAEventBridge correctly passes the ihp_enabled
parameter to calculate_and_schedule_anticipation() in all event-driven scenarios.

These tests would have caught the bug where event-driven recalculations did not
respect the ihp_enabled state, causing preheating to restart even when disabled.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.application import (
    HeatingApplicationService,
)
from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
)


@pytest.fixture
def mock_app_service() -> Mock:
    """Create mock application service."""
    service = Mock(spec=HeatingApplicationService)
    service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
    return service


@pytest.fixture
def get_ihp_enabled_mock() -> Mock:
    """Create mock get_ihp_enabled callback."""
    return Mock(return_value=False)  # Start disabled


@pytest.fixture
def event_bridge(
    hass: HomeAssistant,
    mock_app_service: Mock,
    get_ihp_enabled_mock: Mock,
) -> HAEventBridge:
    """Create HAEventBridge instance for testing."""
    bridge = HAEventBridge(
        hass=hass,
        application_service=mock_app_service,
        vtherm_entity_id="climate.bedroom",
        scheduler_entity_ids=["switch.bedroom_schedule"],
        monitored_entity_ids=["sensor.bedroom_humidity", "sensor.cloud_coverage"],
        entry_id="test_entry_123",
        get_ihp_enabled_func=get_ihp_enabled_mock,
    )
    # Store reference for easier manipulation in tests
    bridge._get_ihp_enabled = get_ihp_enabled_mock
    return bridge


class TestEventBridgeIHPEnabledRespected:
    """Test suite: Event-driven recalculation respects ihp_enabled state."""

    @pytest.mark.asyncio
    async def test_event_driven_recalc_respects_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify that event-driven recalc passes ihp_enabled=False when IHP is disabled.

        Critical test case that would have caught the original bug where scheduler
        entity changes didn't pass ihp_enabled to calculate_and_schedule_anticipation().
        """
        # GIVEN: IHP disabled
        get_ihp_enabled_mock.return_value = False
        event_bridge.setup_listeners()

        # WHEN: Scheduler switch state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: calculate_and_schedule_anticipation called with ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_event_driven_recalc_respects_ihp_enabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify event-driven recalc passes ihp_enabled=True when IHP is enabled."""
        # GIVEN: IHP enabled
        get_ihp_enabled_mock.return_value = True
        event_bridge.setup_listeners()

        # WHEN: Scheduler switch state changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: calculate_and_schedule_anticipation called with ihp_enabled=True
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True

    @pytest.mark.asyncio
    async def test_vtherm_change_respects_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify VTherm change events respect ihp_enabled=False."""
        # GIVEN: IHP disabled and initial VTherm state
        get_ihp_enabled_mock.return_value = False
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 18.5},
        )
        event_bridge.setup_listeners()
        mock_app_service.calculate_and_schedule_anticipation.reset_mock()

        # WHEN: VTherm temperature changes
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 19.0},
        )
        await hass.async_block_till_done()

        # THEN: Recalculation respects ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_vtherm_change_respects_ihp_enabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify VTherm change events respect ihp_enabled=True."""
        # GIVEN: IHP enabled and initial VTherm state
        get_ihp_enabled_mock.return_value = True
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 18.5},
        )
        event_bridge.setup_listeners()
        mock_app_service.calculate_and_schedule_anticipation.reset_mock()

        # WHEN: VTherm temperature changes
        hass.states.async_set(
            "climate.bedroom",
            "heat",
            {"current_temperature": 19.0},
        )
        await hass.async_block_till_done()

        # THEN: Recalculation respects ihp_enabled=True
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True


class TestEventBridgeIHPStateTransitions:
    """Test suite: IHP enabled/disabled state transitions."""

    @pytest.mark.asyncio
    async def test_event_driven_recalc_resumes_when_ihp_reenabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify recalculation resumes when IHP is re-enabled.

        Scenario:
        1. IHP disabled, event triggers (ihp_enabled=False passed)
        2. IHP enabled
        3. Another event triggers (ihp_enabled=True should be passed)
        """
        event_bridge.setup_listeners()

        # STEP 1: IHP disabled, event occurs
        get_ihp_enabled_mock.return_value = False
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # Verify first call had ihp_enabled=False
        call1_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call1_kwargs["ihp_enabled"] is False

        mock_app_service.calculate_and_schedule_anticipation.reset_mock()

        # STEP 2: IHP re-enabled
        get_ihp_enabled_mock.return_value = True

        # STEP 3: Another event triggers
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()

        # Verify second call had ihp_enabled=True
        call2_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call2_kwargs["ihp_enabled"] is True

    @pytest.mark.asyncio
    async def test_multiple_state_transitions(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify correct ihp_enabled value is passed through multiple transitions."""
        event_bridge.setup_listeners()

        transitions = [
            (False, False),  # Disabled -> remains disabled
            (True, True),  # Enabled -> enabled
            (False, False),  # Disabled -> disabled
            (True, True),  # Enabled -> enabled
        ]

        for i, (enabled_state, expected_ihp_enabled) in enumerate(transitions):
            mock_app_service.calculate_and_schedule_anticipation.reset_mock()
            get_ihp_enabled_mock.return_value = enabled_state

            # Trigger an event
            hass.states.async_set("switch.bedroom_schedule", "on" if i % 2 == 0 else "off")
            await hass.async_block_till_done()

            # Verify the mock was called
            mock_app_service.calculate_and_schedule_anticipation.assert_called_once()

            # Verify the correct ihp_enabled was passed
            call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
            assert (
                call_kwargs["ihp_enabled"] == expected_ihp_enabled
            ), f"Transition {i}: Expected ihp_enabled={expected_ihp_enabled}, got {call_kwargs['ihp_enabled']}"


class TestEventBridgeMonitoredEntitiesRespectIHPEnabled:
    """Test suite: Monitored entities (humidity, cloud cover, etc.) respect ihp_enabled."""

    @pytest.mark.asyncio
    async def test_humidity_sensor_change_respects_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify humidity sensor changes respect ihp_enabled=False.

        When IHP is disabled and a monitored entity (like humidity sensor) changes,
        the recalculation should still pass ihp_enabled=False to the application service.
        """
        # GIVEN: IHP disabled
        get_ihp_enabled_mock.return_value = False
        event_bridge.setup_listeners()

        # WHEN: Humidity sensor changes
        hass.states.async_set("sensor.bedroom_humidity", "45")
        await hass.async_block_till_done()

        # THEN: Recalculation passes ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_cloud_cover_change_respects_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify cloud cover sensor changes respect ihp_enabled=False."""
        # GIVEN: IHP disabled
        get_ihp_enabled_mock.return_value = False
        event_bridge.setup_listeners()

        # WHEN: Cloud cover sensor changes
        hass.states.async_set("sensor.cloud_coverage", "25")
        await hass.async_block_till_done()

        # THEN: Recalculation passes ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_humidity_sensor_change_respects_ihp_enabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify humidity sensor changes respect ihp_enabled=True."""
        # GIVEN: IHP enabled
        get_ihp_enabled_mock.return_value = True
        event_bridge.setup_listeners()

        # WHEN: Humidity sensor changes
        hass.states.async_set("sensor.bedroom_humidity", "50")
        await hass.async_block_till_done()

        # THEN: Recalculation passes ihp_enabled=True
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True


class TestEventBridgeMultipleSchedulers:
    """Test suite: Multiple scheduler entities respect ihp_enabled."""

    @pytest.mark.asyncio
    async def test_multiple_scheduler_changes_respect_ihp_disabled(
        self,
        hass: HomeAssistant,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify all scheduler entity changes respect ihp_enabled=False."""
        # GIVEN: Bridge with multiple schedulers, IHP disabled
        get_ihp_enabled_mock.return_value = False
        bridge = HAEventBridge(
            hass=hass,
            application_service=mock_app_service,
            vtherm_entity_id="climate.bedroom",
            scheduler_entity_ids=[
                "switch.bedroom_schedule",
                "switch.bedroom_schedule2",
            ],
            entry_id="test_entry_123",
            get_ihp_enabled_func=get_ihp_enabled_mock,
        )
        bridge.setup_listeners()

        # WHEN: First scheduler changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=False passed
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

        mock_app_service.calculate_and_schedule_anticipation.reset_mock()

        # WHEN: Second scheduler changes
        hass.states.async_set("switch.bedroom_schedule2", "off")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=False still passed
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_multiple_scheduler_changes_respect_ihp_enabled(
        self,
        hass: HomeAssistant,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify all scheduler entity changes respect ihp_enabled=True."""
        # GIVEN: Bridge with multiple schedulers, IHP enabled
        get_ihp_enabled_mock.return_value = True
        bridge = HAEventBridge(
            hass=hass,
            application_service=mock_app_service,
            vtherm_entity_id="climate.bedroom",
            scheduler_entity_ids=[
                "switch.bedroom_schedule",
                "switch.bedroom_schedule2",
            ],
            entry_id="test_entry_123",
            get_ihp_enabled_func=get_ihp_enabled_mock,
        )
        bridge.setup_listeners()

        # WHEN: First scheduler changes
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=True passed
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True

        mock_app_service.calculate_and_schedule_anticipation.reset_mock()

        # WHEN: Second scheduler changes
        hass.states.async_set("switch.bedroom_schedule2", "off")
        await hass.async_block_till_done()

        # THEN: ihp_enabled=True still passed
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True


class TestEventBridgeNoCallableProvided:
    """Test suite: Default behavior when get_ihp_enabled_func is not provided."""

    @pytest.mark.asyncio
    async def test_default_no_get_ihp_enabled_func_provided(
        self,
        hass: HomeAssistant,
        mock_app_service: Mock,
    ) -> None:
        """Verify that when get_ihp_enabled_func is not provided, defaults to True."""
        # GIVEN: Bridge created without get_ihp_enabled_func
        bridge = HAEventBridge(
            hass=hass,
            application_service=mock_app_service,
            vtherm_entity_id="climate.bedroom",
            scheduler_entity_ids=["switch.bedroom_schedule"],
            entry_id="test_entry_123",
            get_ihp_enabled_func=None,  # Explicitly None
        )
        bridge.setup_listeners()

        # WHEN: Event triggers
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: Default behavior should be ihp_enabled=True
        call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True


class TestEventBridgeEdgeCases:
    """Test suite: Edge cases and race conditions."""

    @pytest.mark.asyncio
    async def test_rapid_state_changes_all_respect_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify rapid state changes all pass correct ihp_enabled value.

        This tests for race conditions where state could change between event
        trigger and application service call.
        """
        # GIVEN: IHP disabled
        get_ihp_enabled_mock.return_value = False
        event_bridge.setup_listeners()

        # WHEN: Multiple rapid state changes
        for i in range(3):
            mock_app_service.calculate_and_schedule_anticipation.reset_mock()
            hass.states.async_set("switch.bedroom_schedule", "on" if i % 2 == 0 else "off")
            await hass.async_block_till_done()

            # THEN: Each call has correct ihp_enabled
            call_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
            assert call_kwargs["ihp_enabled"] is False, f"Iteration {i} failed"

    @pytest.mark.asyncio
    async def test_state_change_during_callback_uses_current_value(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_app_service: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        """Verify that the current value of get_ihp_enabled_func is used at call time.

        This is critical: if the state changes between event trigger and async
        execution, the current state should be reflected.
        """
        event_bridge.setup_listeners()

        # GIVEN: IHP starts disabled
        get_ihp_enabled_mock.return_value = False
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        # THEN: First call has ihp_enabled=False
        call1_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call1_kwargs["ihp_enabled"] is False

        # NOW: State changes before second event is processed
        mock_app_service.calculate_and_schedule_anticipation.reset_mock()
        get_ihp_enabled_mock.return_value = True
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()

        # THEN: Second call uses the current (True) value
        call2_kwargs = mock_app_service.calculate_and_schedule_anticipation.call_args[1]
        assert call2_kwargs["ihp_enabled"] is True
