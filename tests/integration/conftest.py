"""Shared fixtures for the integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def flow_environment(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> Generator[AsyncMock]:
    """Let config and options flows load the integration and its dependencies.

    The manifest declares ``recorder`` as a dependency (#192), so opening a flow sets the
    recorder up: ``recorder_mock`` provides an in-memory one. Entries created by a flow are
    not set up for real, so a flow test does not start a coordinator and its timers.
    """
    with patch(
        "custom_components.intelligent_heating_pilot.async_setup_entry",
        new=AsyncMock(return_value=True),
    ) as setup_entry:
        yield setup_entry


@pytest.fixture
async def release_on_teardown(
    hass: HomeAssistant,
) -> AsyncGenerator[Callable[[MockConfigEntry], None]]:
    """Run, after the test, the unload callbacks of the entries it registers.

    ``hass.config_entries.async_unload`` runs them for a loaded entry. Tests that call
    ``async_setup_entry`` or ``async_unload_entry`` directly bypass it, so the startup
    timers registered with ``entry.async_on_unload`` would outlive the test, which the
    Home Assistant test harness reports as lingering timers.
    """
    entries: list[MockConfigEntry] = []
    yield entries.append
    for entry in entries:
        await entry._async_process_on_unload(hass)
