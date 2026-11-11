"""Regression tests: sensors must show the LHS learned by a background extraction.

Before the fix, the end of an extraction only requested a recalculation. The
LHS sensors read the coordinator's caches, which were reloaded only at startup
or on an options change, so after a learning reset they kept showing 2.0 until
Home Assistant restarted, although the anticipation already used the new slopes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_LEARNED_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)

DEVICE_ID = "climate.test_vtherm"
LEARNED_GLOBAL_LHS = 1.78
LEARNED_HOUR = 6
LEARNED_CONTEXTUAL_LHS = 2.4
FORGOTTEN_HOUR = 8
STALE_CONTEXTUAL_LHS = 4.2


@pytest.fixture
def app_after_reset() -> HeatingApplication:
    """Create a HeatingApplication whose caches still hold the post-reset defaults."""
    device_config = DeviceConfig(
        device_id=DEVICE_ID,
        vtherm_entity_id=DEVICE_ID,
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
    )
    app = HeatingApplication(Mock(), device_config)
    app._event_bridge = Mock()
    app._lhs_manager = Mock()
    app._lhs_manager.get_global_lhs = AsyncMock(return_value=LEARNED_GLOBAL_LHS)
    app._lhs_manager.get_learned_contextual_lhs = AsyncMock(
        side_effect=lambda hour: LEARNED_CONTEXTUAL_LHS if hour == LEARNED_HOUR else None
    )
    app._lhs_cache = DEFAULT_LEARNED_SLOPE
    app._contextual_lhs_cache = {FORGOTTEN_HOUR: STALE_CONTEXTUAL_LHS}
    return app


class TestRefreshAfterExtraction:
    """_refresh_caches_and_publish() must reload the caches before publishing."""

    @pytest.mark.asyncio
    async def test_global_lhs_sensor_shows_learned_value(
        self, app_after_reset: HeatingApplication
    ) -> None:
        """The global LHS sensor leaves the 2.0 default once the extraction learned a slope."""
        await app_after_reset._refresh_caches_and_publish()

        assert app_after_reset.get_learned_heating_slope() == LEARNED_GLOBAL_LHS

    @pytest.mark.asyncio
    async def test_contextual_cache_is_rebuilt(self, app_after_reset: HeatingApplication) -> None:
        """Newly learned hours appear and hours no longer learned drop out."""
        await app_after_reset._refresh_caches_and_publish()

        assert app_after_reset._contextual_lhs_cache == {LEARNED_HOUR: LEARNED_CONTEXTUAL_LHS}

    @pytest.mark.asyncio
    async def test_publish_is_forced_after_caches_are_reloaded(
        self, app_after_reset: HeatingApplication
    ) -> None:
        """Sensors refresh even if the anticipation itself did not change."""
        lhs_at_publish: list[float] = []
        app_after_reset._event_bridge.request_forced_publish.side_effect = lambda: (
            lhs_at_publish.append(app_after_reset.get_learned_heating_slope())
        )

        await app_after_reset._refresh_caches_and_publish()

        assert lhs_at_publish == [LEARNED_GLOBAL_LHS]

    @pytest.mark.asyncio
    async def test_failed_global_read_keeps_contextual_refresh(
        self, app_after_reset: HeatingApplication
    ) -> None:
        """A storage error on the global LHS does not block the rest of the refresh."""
        app_after_reset._lhs_manager.get_global_lhs.side_effect = RuntimeError("storage")

        await app_after_reset._refresh_caches_and_publish()

        assert app_after_reset.get_learned_heating_slope() == DEFAULT_LEARNED_SLOPE
        assert app_after_reset._contextual_lhs_cache == {LEARNED_HOUR: LEARNED_CONTEXTUAL_LHS}
        app_after_reset._event_bridge.request_forced_publish.assert_called_once()


class TestOnExtractionComplete:
    """The synchronous extraction callback must schedule the refresh."""

    @pytest.mark.asyncio
    async def test_callback_schedules_refresh(self, app_after_reset: HeatingApplication) -> None:
        """The lifecycle manager's callback ends with sensors showing the learned LHS."""
        scheduled: list[asyncio.Task] = []
        app_after_reset.hass.async_create_task = lambda coro: scheduled.append(
            asyncio.ensure_future(coro)
        )

        app_after_reset._on_extraction_complete()
        await asyncio.gather(*scheduled)

        assert app_after_reset.get_learned_heating_slope() == LEARNED_GLOBAL_LHS
        app_after_reset._event_bridge.request_forced_publish.assert_called_once()
