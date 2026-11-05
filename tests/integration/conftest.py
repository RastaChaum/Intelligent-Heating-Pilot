"""Shared fixtures for the integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.recorder import Recorder


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
