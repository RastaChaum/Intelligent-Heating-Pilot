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


def test_startup_publish_goes_through_the_bridge(app: HeatingApplication) -> None:
    """Only the bridge fires the event the sensors refresh on."""
    app.request_startup_publish()

    app._event_bridge.request_forced_publish.assert_called_once()


def test_startup_publish_without_a_bridge_does_nothing(app: HeatingApplication) -> None:
    """The application may be unloaded or not loaded yet when the timer fires."""
    app._event_bridge = None

    app.request_startup_publish()
