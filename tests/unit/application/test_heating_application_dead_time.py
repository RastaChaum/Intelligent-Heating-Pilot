"""Tests for HeatingApplication dead time methods.

Tests for methods:
- get_effective_dead_time() - returns float based on auto_learning flag
- get_current_dead_time() - returns Optional[float] of raw learned value
- is_auto_learning_enabled() - returns bool from device config
- async_update() - never stores the learned dead time (#224)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.const import EVENT_DEAD_TIME_UPDATED
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.heating_application import (
    HeatingApplication,
)


@pytest.fixture
def device_config_auto_learning_enabled() -> DeviceConfig:
    """Create device config with auto_learning enabled."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
        auto_learning=True,
        dead_time_minutes=5.0,
    )


@pytest.fixture
def device_config_auto_learning_disabled() -> DeviceConfig:
    """Create device config with auto_learning disabled."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
        auto_learning=False,
        dead_time_minutes=5.0,
    )


@pytest.fixture
def mock_lhs_storage() -> Mock:
    """Create mock ILhsStorage."""
    storage = Mock()
    storage.get_learned_dead_time = AsyncMock(return_value=None)
    storage.get_learned_heating_slope = AsyncMock(return_value=2.5)
    return storage


def make_app(device_config: DeviceConfig, lhs_storage: Mock) -> HeatingApplication:
    """Construct a real HeatingApplication with mocked HA and injected storage.

    Bypasses async_load() so HA adapters are never created; only the attributes
    exercised by get_effective_dead_time / get_current_dead_time are needed.
    """
    mock_hass = Mock()
    app = HeatingApplication(mock_hass, device_config)
    # Inject mock storage directly — mirrors what async_load() would set
    app._lhs_storage = lhs_storage
    return app


class TestHeatingApplicationDeadTimeMethods:
    """Test suite for HeatingApplication dead time methods."""

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_learned_when_auto_learning_true(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_effective_dead_time returns learned value when auto_learning is enabled.

        When:
        - auto_learning = True
        - learned_dead_time = 6.5

        Then:
        - get_effective_dead_time() returns 6.5
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        result = await app.get_effective_dead_time()

        assert result == pytest.approx(6.5)
        mock_lhs_storage.get_learned_dead_time.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_configured_when_auto_learning_false(
        self,
        device_config_auto_learning_disabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_effective_dead_time returns configured value when auto_learning is disabled.

        When:
        - auto_learning = False
        - configured dead_time_minutes = 5.0
        - learned_dead_time = 6.5 (should be ignored)

        Then:
        - get_effective_dead_time() returns 5.0 (configured value)
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)
        app = make_app(device_config_auto_learning_disabled, mock_lhs_storage)

        result = await app.get_effective_dead_time()

        assert result == pytest.approx(5.0)
        # Storage must NOT be consulted when auto_learning is off
        mock_lhs_storage.get_learned_dead_time.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_fallback_to_configured_when_none(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_effective_dead_time falls back to configured when learned value is None.

        When:
        - auto_learning = True
        - learned_dead_time = None (not yet learned)
        - configured dead_time_minutes = 5.0

        Then:
        - get_effective_dead_time() returns 5.0 (fallback to configured)
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        result = await app.get_effective_dead_time()

        assert result == pytest.approx(5.0)
        mock_lhs_storage.get_learned_dead_time.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_current_dead_time_returns_raw_learned_value(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_current_dead_time returns raw learned value (without flag check).

        This method bypasses the auto_learning flag check and returns
        whatever is stored (or None if nothing learned yet).

        When:
        - learned_dead_time = 6.5

        Then:
        - get_current_dead_time() returns 6.5
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        result = await app.get_current_dead_time()

        assert result == pytest.approx(6.5)
        mock_lhs_storage.get_learned_dead_time.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_current_dead_time_returns_none_when_not_learned(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_current_dead_time returns None when nothing learned yet.

        When:
        - learned_dead_time = None

        Then:
        - get_current_dead_time() returns None
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        result = await app.get_current_dead_time()

        assert result is None
        mock_lhs_storage.get_learned_dead_time.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_float_not_optional(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """get_effective_dead_time always returns float (never None).

        This is the key difference from get_current_dead_time():
        - get_effective_dead_time() -> float (always)
        - get_current_dead_time() -> float | None (may be None)
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        result = await app.get_effective_dead_time()

        # Even with None learned, should return configured fallback (5.0), not None
        assert isinstance(result, float)
        assert result is not None

    def test_is_auto_learning_enabled_method(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """is_auto_learning_enabled() returns True when device config has auto_learning=True."""
        app = make_app(device_config_auto_learning_enabled, mock_lhs_storage)

        assert app.is_auto_learning_enabled() is True

    def test_is_auto_learning_enabled_when_disabled(
        self,
        device_config_auto_learning_disabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """is_auto_learning_enabled() returns False when device config has auto_learning=False."""
        app = make_app(device_config_auto_learning_disabled, mock_lhs_storage)

        assert app.is_auto_learning_enabled() is False


def make_updating_app(
    device_config: DeviceConfig, lhs_storage: Mock, anticipation_data: dict[str, Any] | None
) -> HeatingApplication:
    """Construct an application whose anticipation returns the given data."""
    lhs_storage.set_learned_dead_time = AsyncMock()
    app = make_app(device_config, lhs_storage)
    app._orchestrator = Mock()
    app._orchestrator.calculate_and_schedule_anticipation = AsyncMock(
        return_value=anticipation_data
    )
    app._lhs_manager = None
    return app


def dead_time_events(app: HeatingApplication) -> list[Any]:
    """Return the dead time update events fired by the application."""
    return [
        call
        for call in app.hass.bus.async_fire.call_args_list
        if call.args[0] == EVENT_DEAD_TIME_UPDATED
    ]


class TestUpdateNeverStoresDeadTime:
    """async_update() leaves the learned dead time to the cycle extraction (#224).

    The update stored whichever dead time the anticipation had used: the configured
    one when nothing was learned, which then took precedence over the configured
    value and undid reset_learning; and the stored value itself after each restart,
    logged and announced as an update.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "anticipation_dead_time",
        [
            pytest.param(0.0, id="default configured dead time"),
            pytest.param(5.0, id="configured dead time"),
            pytest.param(6.5, id="stored dead time after a restart"),
            pytest.param(8.0, id="average of the target window cycles"),
        ],
    )
    async def test_dead_time_not_stored_nor_announced(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
        anticipation_dead_time: float,
    ) -> None:
        """Whatever dead time the anticipation used, nothing is stored or announced."""
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)
        app = make_updating_app(
            device_config_auto_learning_enabled,
            mock_lhs_storage,
            {"dead_time": anticipation_dead_time},
        )

        await app.async_update()
        await app.async_update()

        mock_lhs_storage.set_learned_dead_time.assert_not_awaited()
        assert dead_time_events(app) == []

    @pytest.mark.asyncio
    async def test_configured_dead_time_not_stored_when_auto_learning_disabled(
        self,
        device_config_auto_learning_disabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """The configured dead time used without auto-learning is never stored as learned."""
        app = make_updating_app(
            device_config_auto_learning_disabled, mock_lhs_storage, {"dead_time": 5.0}
        )

        await app.async_update()

        mock_lhs_storage.set_learned_dead_time.assert_not_awaited()
        assert dead_time_events(app) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("anticipation_data", [None, {}, {"dead_time": None}])
    async def test_missing_anticipation_data_is_harmless(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
        anticipation_data: dict[str, Any] | None,
    ) -> None:
        """No anticipation (no schedule, no sensor) does not touch the dead time either."""
        app = make_updating_app(
            device_config_auto_learning_enabled, mock_lhs_storage, anticipation_data
        )

        await app.async_update()

        mock_lhs_storage.set_learned_dead_time.assert_not_awaited()
        assert dead_time_events(app) == []
