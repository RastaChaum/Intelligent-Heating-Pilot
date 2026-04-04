"""Regression tests for HeatingApplication LHS cache refresh after extraction.

Bug: After background extraction discovered new heating cycles and updated
the LHS in LhsLifecycleManager, the HeatingApplication._lhs_cache (which
sensors read from) was never refreshed. The sensor always displayed the
stale default value (2.0 °C/h).

Root cause: _on_extraction_complete() only triggered event bridge
recalculation but did not refresh _lhs_cache first. The sensor
reads from _lhs_cache via get_learned_heating_slope(), so it
always returned the stale startup value.

Fix: _on_extraction_complete() now schedules _refresh_and_recalculate()
which calls refresh_caches() (updating _lhs_cache from LhsLifecycleManager)
before triggering the event bridge recalculation.

These tests FAIL with the buggy code, PASS with the fix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)


@pytest.fixture
def device_config() -> DeviceConfig:
    """Create standard device config for testing."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
        auto_learning=True,
        dead_time_minutes=5.0,
    )


@pytest.fixture
def mock_lhs_manager() -> Mock:
    """Create mock LhsLifecycleManager returning updated LHS."""
    manager = Mock()
    manager.get_global_lhs = AsyncMock(return_value=3.5)
    return manager


@pytest.fixture
def mock_event_bridge() -> Mock:
    """Create mock HAEventBridge."""
    bridge = Mock()
    bridge._request_recalculate = Mock()
    return bridge


def make_app(
    device_config: DeviceConfig,
    lhs_manager: Mock,
    event_bridge: Mock | None = None,
) -> HeatingApplication:
    """Construct HeatingApplication with mocked dependencies.

    Bypasses async_load(); only injects what _on_extraction_complete needs.
    """
    mock_hass = Mock()
    mock_hass.async_create_task = Mock(side_effect=lambda coro: coro)
    app = HeatingApplication(mock_hass, device_config)
    app._lhs_manager = lhs_manager
    app._event_bridge = event_bridge
    return app


class TestLHSCacheRefreshAfterExtraction:
    """Regression tests for LHS cache refresh on extraction complete.

    Bug: sensor.intelligent_heating_pilot_global_learned_heating_slope
    was stuck at default 2°C/h because _lhs_cache was never updated
    after background extraction.
    """

    @pytest.mark.asyncio
    async def test_refresh_and_recalculate_updates_lhs_cache(
        self,
        device_config: DeviceConfig,
        mock_lhs_manager: Mock,
        mock_event_bridge: Mock,
    ) -> None:
        """_refresh_and_recalculate updates _lhs_cache before triggering recalculation.

        FAILS with buggy code (_lhs_cache stays at 2.0 default)
        PASSES with fix (_lhs_cache updated to 3.5 from LhsLifecycleManager)
        """
        app = make_app(device_config, mock_lhs_manager, mock_event_bridge)
        # Simulate stale cache (default value at startup)
        app._lhs_cache = 2.0

        # WHEN: _refresh_and_recalculate is called (triggered by extraction complete)
        await app._refresh_and_recalculate()

        # THEN: _lhs_cache is updated with value from LhsLifecycleManager
        assert app._lhs_cache == 3.5
        mock_lhs_manager.get_global_lhs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_and_recalculate_triggers_event_bridge(
        self,
        device_config: DeviceConfig,
        mock_lhs_manager: Mock,
        mock_event_bridge: Mock,
    ) -> None:
        """_refresh_and_recalculate triggers event bridge recalculation after cache update.

        Ensures sensors are notified after _lhs_cache has been refreshed.
        """
        app = make_app(device_config, mock_lhs_manager, mock_event_bridge)

        await app._refresh_and_recalculate()

        mock_event_bridge._request_recalculate.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_and_recalculate_without_event_bridge(
        self,
        device_config: DeviceConfig,
        mock_lhs_manager: Mock,
    ) -> None:
        """_refresh_and_recalculate works without event bridge (no crash).

        Edge case: event bridge might not be set up yet during startup.
        """
        app = make_app(device_config, mock_lhs_manager, event_bridge=None)
        app._lhs_cache = 2.0

        # Should not raise
        await app._refresh_and_recalculate()

        # Cache still updated
        assert app._lhs_cache == 3.5

    @pytest.mark.asyncio
    async def test_refresh_and_recalculate_without_lhs_manager(
        self,
        device_config: DeviceConfig,
        mock_event_bridge: Mock,
    ) -> None:
        """_refresh_and_recalculate handles missing LHS manager gracefully.

        Edge case: _lhs_manager is None (e.g., partially initialized).
        """
        app = make_app(device_config, lhs_manager=Mock(), event_bridge=mock_event_bridge)
        app._lhs_manager = None
        app._lhs_cache = 2.0

        # Should not raise
        await app._refresh_and_recalculate()

        # Cache stays at default (no manager to refresh from)
        assert app._lhs_cache == 2.0
        # Event bridge still triggered (recalculation should still happen)
        mock_event_bridge._request_recalculate.assert_called_once()

    def test_on_extraction_complete_schedules_async_task(
        self,
        device_config: DeviceConfig,
        mock_lhs_manager: Mock,
        mock_event_bridge: Mock,
    ) -> None:
        """_on_extraction_complete creates an async task for cache refresh + recalculate.

        Verifies that the synchronous callback delegates to async properly
        via hass.async_create_task.
        """
        app = make_app(device_config, mock_lhs_manager, mock_event_bridge)

        app._on_extraction_complete()

        app.hass.async_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_sensor_reads_updated_lhs_after_extraction(
        self,
        device_config: DeviceConfig,
        mock_lhs_manager: Mock,
        mock_event_bridge: Mock,
    ) -> None:
        """End-to-end: get_learned_heating_slope returns updated value after extraction.

        This is the complete flow that the sensor exercises:
        1. _lhs_cache starts at default 2.0
        2. Background extraction completes
        3. _refresh_and_recalculate runs
        4. get_learned_heating_slope() returns the updated value

        FAILS with buggy code (returns 2.0)
        PASSES with fix (returns 3.5)
        """
        app = make_app(device_config, mock_lhs_manager, mock_event_bridge)
        app._lhs_cache = 2.0

        # Verify initial stale value
        assert app.get_learned_heating_slope() == 2.0

        # Simulate extraction complete → cache refresh
        await app._refresh_and_recalculate()

        # Sensor reads the updated value
        assert app.get_learned_heating_slope() == 3.5
