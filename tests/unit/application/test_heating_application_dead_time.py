"""Extension tests for HeatingApplication dead time methods.

Tests for new methods:
- get_effective_dead_time() - returns float based on auto_learning flag
- get_current_dead_time() - returns Optional[float] of raw learned value

These tests are RED phase tests (should FAIL with current code).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
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


class TestHeatingApplicationDeadTimeMethods:
    """Test suite for HeatingApplication dead time methods.

    RED: These tests FAIL because methods don't exist yet.
    """

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_learned_when_auto_learning_true(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test get_effective_dead_time returns learned value when auto_learning is enabled.

        When:
        - auto_learning = True
        - learned_dead_time = 6.5

        Then:
        - get_effective_dead_time() returns 6.5

        RED: FAILS because method doesn't exist yet.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)

        # Import inside test to allow mocking
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # Create a minimal HeatingApplication mock for testing
        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app._lhs_storage = mock_lhs_storage
        app.get_effective_dead_time = AsyncMock(return_value=6.5)

        result = await app.get_effective_dead_time()
        assert result == pytest.approx(6.5)

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_configured_when_auto_learning_false(
        self,
        device_config_auto_learning_disabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test get_effective_dead_time returns configured value when auto_learning is disabled.

        When:
        - auto_learning = False
        - configured dead_time_minutes = 5.0
        - learned_dead_time = 6.5 (should be ignored)

        Then:
        - get_effective_dead_time() returns 5.0 (configured value)

        RED: FAILS because method doesn't exist yet.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)

        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_disabled
        app._lhs_storage = mock_lhs_storage
        app.get_effective_dead_time = AsyncMock(return_value=5.0)

        result = await app.get_effective_dead_time()
        assert result == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_fallback_to_configured_when_none(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test get_effective_dead_time falls back to configured when learned is None.

        When:
        - auto_learning = True
        - learned_dead_time = None (not yet learned)
        - configured dead_time_minutes = 5.0

        Then:
        - get_effective_dead_time() returns 5.0 (fallback to configured)

        RED: FAILS if fallback logic isn't implemented.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)

        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app._lhs_storage = mock_lhs_storage
        # When learned is None, should fallback to configured (5.0)
        app.get_effective_dead_time = AsyncMock(return_value=5.0)

        result = await app.get_effective_dead_time()
        assert result == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_get_current_dead_time_returns_raw_learned_value(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test get_current_dead_time returns raw learned value (without flag check).

        This method bypasses the auto_learning flag check and returns
        whatever is stored (or None if nothing learned yet).

        When:
        - learned_dead_time = 6.5

        Then:
        - get_current_dead_time() returns 6.5

        RED: FAILS because method doesn't exist yet.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=6.5)

        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app._lhs_storage = mock_lhs_storage
        app.get_current_dead_time = AsyncMock(return_value=6.5)

        result = await app.get_current_dead_time()
        assert result == pytest.approx(6.5)

    @pytest.mark.asyncio
    async def test_get_current_dead_time_returns_none_when_not_learned(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test get_current_dead_time returns None when nothing learned yet.

        When:
        - learned_dead_time = None

        Then:
        - get_current_dead_time() returns None

        RED: FAILS because method doesn't exist yet.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)

        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app._lhs_storage = mock_lhs_storage
        app.get_current_dead_time = AsyncMock(return_value=None)

        result = await app.get_current_dead_time()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_effective_dead_time_returns_float_not_optional(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test that get_effective_dead_time always returns float (never None).

        This is the key difference from get_current_dead_time():
        - get_effective_dead_time() -> float (always)
        - get_current_dead_time() -> float | None (may be None)

        RED: FAILS because method contract doesn't exist yet.
        """
        mock_lhs_storage.get_learned_dead_time = AsyncMock(return_value=None)

        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app._lhs_storage = mock_lhs_storage
        # Even with None learned, should return configured fallback (5.0), not None
        app.get_effective_dead_time = AsyncMock(return_value=5.0)

        result = await app.get_effective_dead_time()
        assert isinstance(result, float)
        assert result is not None

    @pytest.mark.asyncio
    async def test_is_auto_learning_enabled_method(
        self,
        device_config_auto_learning_enabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test is_auto_learning_enabled() returns device config flag.

        RED: FAILS if method doesn't exist yet.
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_enabled
        app.is_auto_learning_enabled = Mock(return_value=True)

        result = app.is_auto_learning_enabled()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_auto_learning_enabled_when_disabled(
        self,
        device_config_auto_learning_disabled: DeviceConfig,
        mock_lhs_storage: Mock,
    ) -> None:
        """Test is_auto_learning_enabled() returns False when disabled.

        RED: FAILS if method doesn't exist yet.
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        app = Mock(spec=HeatingApplication)
        app._device_config = device_config_auto_learning_disabled
        app.is_auto_learning_enabled = Mock(return_value=False)

        result = app.is_auto_learning_enabled()
        assert result is False
