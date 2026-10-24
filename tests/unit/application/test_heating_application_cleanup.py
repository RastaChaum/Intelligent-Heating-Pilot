"""Tests for HeatingApplication.async_cleanup().

The anticipation timer is registered with Home Assistant and outlives the
application object unless cleanup cancels it explicitly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)


@pytest.mark.asyncio
async def test_cleanup_cancels_pending_anticipation_timer() -> None:
    """Unloading the entry must cancel the anticipation timer of this instance."""
    device_config = DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
    )
    app = HeatingApplication(Mock(), device_config)
    orchestrator = Mock()
    orchestrator.cancel_pending_anticipation = AsyncMock()
    app._orchestrator = orchestrator

    await app.async_cleanup()

    orchestrator.cancel_pending_anticipation.assert_awaited_once()
