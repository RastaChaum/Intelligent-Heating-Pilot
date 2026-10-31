"""Regression tests for issue #226: contextual LHS accessor must not fall back to global.

Before the fix, HeatingApplication.get_contextual_learned_heating_slope returned
the global LHS for any hour without a learned contextual value, so the
"Contextual Learned Heating Slope" sensor displayed the global slope as if it
had been learned for that hour.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)

DEVICE_ID = "climate.test_vtherm"
LEARNED_GLOBAL_LHS = 1.78
LEARNED_CONTEXTUAL_LHS = 2.4
LEARNED_HOUR = 6
UNLEARNED_HOUR = 23
OUT_OF_RANGE_HOURS = (-1, 24)
SLOT_AFTER_HALF_HOUR = datetime(2026, 1, 15, 6, 45)
NEAREST_HOUR_OF_SLOT = 7


@pytest.fixture
def app_with_learned_global_lhs() -> HeatingApplication:
    """Create a HeatingApplication with a learned global LHS and one contextual hour."""
    device_config = DeviceConfig(
        device_id=DEVICE_ID,
        vtherm_entity_id=DEVICE_ID,
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
    )
    app = HeatingApplication(Mock(), device_config)
    app._lhs_cache = LEARNED_GLOBAL_LHS
    app._contextual_lhs_cache = {LEARNED_HOUR: LEARNED_CONTEXTUAL_LHS}
    return app


class TestGetContextualLearnedHeatingSlope:
    """The accessor only exposes values actually learned for the requested hour."""

    def test_returns_learned_value_for_learned_hour(
        self, app_with_learned_global_lhs: HeatingApplication
    ) -> None:
        """A learned contextual value is returned as is."""
        result = app_with_learned_global_lhs.get_contextual_learned_heating_slope(LEARNED_HOUR)

        assert result == LEARNED_CONTEXTUAL_LHS

    def test_returns_none_for_hour_without_learned_value(
        self, app_with_learned_global_lhs: HeatingApplication
    ) -> None:
        """An unlearned hour yields None, never the global LHS."""
        result = app_with_learned_global_lhs.get_contextual_learned_heating_slope(UNLEARNED_HOUR)

        assert result is None

    @pytest.mark.parametrize("hour", OUT_OF_RANGE_HOURS)
    def test_returns_none_for_out_of_range_hour(
        self, app_with_learned_global_lhs: HeatingApplication, hour: int
    ) -> None:
        """An invalid hour has no contextual value either."""
        result = app_with_learned_global_lhs.get_contextual_learned_heating_slope(hour)

        assert result is None


class TestContextualCacheAfterUpdate:
    """The update caches the slope of the hour the sensor will read (#214)."""

    @pytest.mark.asyncio
    async def test_slot_after_half_hour_caches_the_next_hour(
        self, app_with_learned_global_lhs: HeatingApplication
    ) -> None:
        """A 06:45 slot reads hour 7: that is the hour reloaded for the sensor."""
        app = app_with_learned_global_lhs
        app._orchestrator = Mock()
        app._orchestrator.calculate_and_schedule_anticipation = AsyncMock(
            return_value={"next_schedule_time": SLOT_AFTER_HALF_HOUR}
        )
        app._lhs_manager = Mock()
        app._lhs_manager.get_global_lhs = AsyncMock(return_value=LEARNED_GLOBAL_LHS)
        app._lhs_manager.get_learned_contextual_lhs = AsyncMock(
            side_effect={NEAREST_HOUR_OF_SLOT: LEARNED_CONTEXTUAL_LHS}.get
        )

        await app._async_update_locked()

        assert (
            app.get_contextual_learned_heating_slope(NEAREST_HOUR_OF_SLOT) == LEARNED_CONTEXTUAL_LHS
        )
