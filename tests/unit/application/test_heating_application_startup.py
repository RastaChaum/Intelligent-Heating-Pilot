"""Unit tests for how HeatingApplication behaves while Home Assistant starts."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import CoreState

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import HeatingApplication

DEVICE_ID = "climate.test_vtherm"


@pytest.fixture
def app() -> HeatingApplication:
    """Create a HeatingApplication with its collaborators replaced at the layer boundary."""
    device_config = DeviceConfig(
        device_id=DEVICE_ID,
        vtherm_entity_id=DEVICE_ID,
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
    )
    application = HeatingApplication(Mock(), device_config)
    application._orchestrator = AsyncMock()
    application._orchestrator.calculate_and_schedule_anticipation.return_value = {}
    application._event_bridge = Mock()
    return application


@pytest.mark.parametrize("state", [CoreState.not_running, CoreState.starting])
async def test_update_is_deferred_until_ha_has_started(
    app: HeatingApplication, state: CoreState
) -> None:
    """The delayed update is timed from setup, so a slow startup can outlast it."""
    app.hass.state = state

    await app.async_update()

    app._orchestrator.calculate_and_schedule_anticipation.assert_not_called()


async def test_update_runs_once_ha_has_started(app: HeatingApplication) -> None:
    """Updates are unaffected once Home Assistant runs."""
    app.hass.state = CoreState.running

    await app.async_update()

    app._orchestrator.calculate_and_schedule_anticipation.assert_awaited_once()


def test_startup_publish_refreshes_caches_before_publishing(app: HeatingApplication) -> None:
    """The startup publish takes the same path as other forced publishes.

    The sensors read the caches held by the application, so they are reloaded before
    the bridge fires the event the sensors refresh on.
    """
    app._refresh_caches_and_publish = Mock(return_value="refresh-and-publish")

    app.request_startup_publish()

    app.hass.async_create_task.assert_called_once_with("refresh-and-publish")


async def test_refresh_and_publish_reloads_caches_then_forces_publish(
    app: HeatingApplication,
) -> None:
    """Caches first, so the event reaches sensors that read up-to-date values."""
    calls: list[str] = []
    app.refresh_caches = AsyncMock(side_effect=lambda: calls.append("refresh"))
    app._event_bridge.request_forced_publish.side_effect = lambda: calls.append("publish")

    await app._refresh_caches_and_publish()

    assert calls == ["refresh", "publish"]


async def test_refresh_and_publish_without_a_bridge_only_refreshes(
    app: HeatingApplication,
) -> None:
    """The application may be unloaded or not loaded yet when the timer fires."""
    app.refresh_caches = AsyncMock()
    app._event_bridge = None

    await app._refresh_caches_and_publish()

    app.refresh_caches.assert_awaited_once()
