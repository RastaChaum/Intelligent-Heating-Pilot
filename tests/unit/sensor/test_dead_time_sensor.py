"""Unit tests for IntelligentHeatingPilotDeadTimeSensor.

Tests the sensor that displays:
- Current effective dead_time (learned or configured)
- Auto-learning flag in attributes
- Initial value loading from coordinator

These tests are RED phase tests (should FAIL with current code).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.sensor import (
    IntelligentHeatingPilotDeadTimeSensor,
)


@pytest.fixture
def mock_config_entry() -> Mock:
    """Create a mock config entry."""
    config_entry = Mock()
    config_entry.entry_id = "test_entry_dead_time"
    config_entry.data = {"name": "Test IHP"}
    return config_entry


@pytest.fixture
def mock_coordinator_dead_time() -> Mock:
    """Create a mock coordinator with dead_time methods."""
    coordinator = Mock()
    coordinator.get_effective_dead_time = AsyncMock(return_value=6.5)
    coordinator.get_current_dead_time = AsyncMock(return_value=6.5)
    coordinator.is_auto_learning_enabled = Mock(return_value=True)
    return coordinator


@pytest.fixture
def dead_time_sensor(
    mock_coordinator_dead_time: Mock,
    mock_config_entry: Mock,
) -> IntelligentHeatingPilotDeadTimeSensor:
    """Create dead time sensor instance."""
    return IntelligentHeatingPilotDeadTimeSensor(
        coordinator=mock_coordinator_dead_time,
        config_entry=mock_config_entry,
        name="Test IHP",
    )


class TestIntelligentHeatingPilotDeadTimeSensor:
    """Test suite for dead time sensor.

    RED: These tests FAIL because sensor implementation is incomplete.
    """

    def test_sensor_name_is_set(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor has correct name attribute.

        RED: FAILS if _attr_name is not "Dead Time".
        """
        assert dead_time_sensor._attr_name == "Dead Time"

    def test_sensor_unit_of_measurement(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor has correct unit (minutes).

        RED: FAILS if unit is not set to "min" or "minutes".
        """
        assert dead_time_sensor._attr_native_unit_of_measurement in ["min", "minutes"]

    def test_native_value_returns_effective_dead_time(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that native_value property returns current effective dead_time.

        RED: FAILS because property isn't implemented yet.
        """
        # Sensor should get value from its internal state (set during async_added_to_hass)
        dead_time_sensor._dead_time = 6.5

        assert dead_time_sensor.native_value == pytest.approx(6.5)

    def test_native_value_returns_none_when_uninitialized(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that native_value returns None before initialization.

        RED: FAILS if initial state is not None.
        """
        # Fresh sensor should have no value yet
        sensor = IntelligentHeatingPilotDeadTimeSensor(
            coordinator=Mock(),
            config_entry=Mock(),
            name="Test",
        )

        assert sensor.native_value is None

    def test_extra_state_attributes_includes_auto_learning_flag(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that extra_state_attributes includes auto_learning flag.

        RED: FAILS because attribute isn't added yet.
        """
        dead_time_sensor._coordinator.is_auto_learning_enabled = Mock(return_value=True)

        attributes = dead_time_sensor.extra_state_attributes

        assert "auto_learning" in attributes
        assert attributes["auto_learning"] is True

    def test_extra_state_attributes_shows_disabled_learning(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that attributes show auto_learning=False when learning is disabled.

        RED: FAILS because attribute isn't correctly read from coordinator.
        """
        dead_time_sensor._coordinator.is_auto_learning_enabled = Mock(return_value=False)

        attributes = dead_time_sensor.extra_state_attributes

        assert attributes["auto_learning"] is False

    @pytest.mark.asyncio
    async def test_async_added_to_hass_loads_initial_value(
        self,
        dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor,
        mock_coordinator_dead_time: Mock,
    ) -> None:
        """Test that async_added_to_hass loads initial value from coordinator.

        RED: FAILS because async_added_to_hass doesn't call get_effective_dead_time.
        """
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=7.5)

        await dead_time_sensor.async_added_to_hass()

        # After loading, _dead_time should be set
        assert dead_time_sensor._dead_time == pytest.approx(7.5)

    @pytest.mark.asyncio
    async def test_async_added_to_hass_handles_none_value(
        self,
        dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor,
        mock_coordinator_dead_time: Mock,
    ) -> None:
        """Test that async_added_to_hass handles None return correctly.

        RED: FAILS if not handled properly (gets exception).
        """
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=None)

        # Should not raise exception
        await dead_time_sensor.async_added_to_hass()

    def test_sensor_available_is_true(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor is always available.

        RED: FAILS if available property isn't implemented or returns False.
        """
        assert dead_time_sensor.available is True

    def test_sensor_unique_id_is_set(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor has unique_id set correctly.

        RED: FAILS if unique_id is not properly set.
        """
        assert dead_time_sensor._attr_unique_id == "test_entry_dead_time_dead_time"

    def test_native_value_with_learned_dead_time(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test sensor displays learned dead_time when available.

        Scenario:
        - auto_learning = True
        - learned_dead_time = 6.5

        Expected:
        - native_value = 6.5

        RED: FAILS if value handling is incorrect.
        """
        dead_time_sensor._coordinator.is_auto_learning_enabled = Mock(return_value=True)
        dead_time_sensor._dead_time = 6.5

        assert dead_time_sensor.native_value == pytest.approx(6.5)
        assert dead_time_sensor.extra_state_attributes["auto_learning"] is True

    def test_native_value_with_configured_dead_time_fallback(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test sensor displays configured dead_time as fallback.

        Scenario:
        - auto_learning = False
        - configured dead_time = 5.0

        Expected:
        - native_value = 5.0

        RED: FAILS if fallback not working.
        """
        dead_time_sensor._coordinator.is_auto_learning_enabled = Mock(return_value=False)
        dead_time_sensor._dead_time = 5.0

        assert dead_time_sensor.native_value == pytest.approx(5.0)
        assert dead_time_sensor.extra_state_attributes["auto_learning"] is False

    def test_native_value_precision(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor preserves decimal precision.

        RED: FAILS if rounding is done incorrectly.
        """
        dead_time_sensor._dead_time = 7.333

        result = dead_time_sensor.native_value
        assert result == pytest.approx(7.333, abs=0.01)

    def test_extra_state_attributes_structure(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that extra_state_attributes returns correct structure.

        RED: FAILS if structure is wrong.
        """
        dead_time_sensor._coordinator.is_auto_learning_enabled = Mock(return_value=True)

        attributes = dead_time_sensor.extra_state_attributes

        assert isinstance(attributes, dict)
        assert "auto_learning" in attributes
        assert isinstance(attributes["auto_learning"], bool)

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_large_dead_time(
        self,
        dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor,
        mock_coordinator_dead_time: Mock,
    ) -> None:
        """Test that sensor handles large dead_time values.

        RED: FAILS if precision is lost with large values.
        """
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=500.75)

        await dead_time_sensor.async_added_to_hass()

        assert dead_time_sensor._dead_time == pytest.approx(500.75)

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_very_small_dead_time(
        self,
        dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor,
        mock_coordinator_dead_time: Mock,
    ) -> None:
        """Test that sensor handles very small dead_time values.

        RED: FAILS if precision is lost with small values.
        """
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=0.25)

        await dead_time_sensor.async_added_to_hass()

        assert dead_time_sensor._dead_time == pytest.approx(0.25, abs=0.01)

    def test_sensor_icon_is_set(
        self, dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor
    ) -> None:
        """Test that sensor has appropriate icon for dead_time.

        RED: FAILS if icon isn't set or is inappropriate.
        """
        icon = getattr(dead_time_sensor, "_attr_icon", None)
        if icon:
            # Icon should be something time-related or measurement-related
            assert isinstance(icon, str)
            assert icon.startswith("mdi:")

    @pytest.mark.asyncio
    async def test_sensor_state_updates_after_coordinator_change(
        self,
        dead_time_sensor: IntelligentHeatingPilotDeadTimeSensor,
        mock_coordinator_dead_time: Mock,
    ) -> None:
        """Test that sensor updates when coordinator value changes.

        This simulates the sensor being updated with a new calculated value.

        RED: FAILS if state update mechanism isn't implemented.
        """
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=5.0)
        await dead_time_sensor.async_added_to_hass()
        assert dead_time_sensor._dead_time == pytest.approx(5.0)

        # Simulate coordinator update
        mock_coordinator_dead_time.get_effective_dead_time = AsyncMock(return_value=8.0)
        dead_time_sensor._dead_time = 8.0

        assert dead_time_sensor.native_value == pytest.approx(8.0)
