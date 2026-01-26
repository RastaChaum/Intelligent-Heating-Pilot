"""Unit tests for IHP Enable Switch entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch
import pytest

from custom_components.intelligent_heating_pilot.switch import (
    IntelligentHeatingPilotEnableSwitch,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = Mock()
    coordinator.is_ihp_enabled = Mock(return_value=True)
    coordinator.set_ihp_enabled = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = Mock()
    config_entry.entry_id = "test_entry_123"
    config_entry.data = {"name": "Test IHP"}
    return config_entry


@pytest.fixture
def switch_entity(mock_coordinator, mock_config_entry):
    """Create a switch entity for testing."""
    return IntelligentHeatingPilotEnableSwitch(
        coordinator=mock_coordinator,
        config_entry=mock_config_entry,
        name="Test IHP",
    )


class TestIntelligentHeatingPilotEnableSwitch:
    """Test suite for IHP enable/disable switch."""

    def test_switch_initialization(self, switch_entity, mock_coordinator):
        """Test that switch initializes with correct state."""
        assert switch_entity.is_on is True
        assert switch_entity.name == "IHP Preheating"
        assert switch_entity.icon == "mdi:home-thermometer"
        mock_coordinator.is_ihp_enabled.assert_called_once()

    def test_switch_unique_id(self, switch_entity):
        """Test that switch has correct unique ID."""
        assert switch_entity.unique_id == "test_entry_123_preheating_enabled"

    def test_switch_device_info(self, switch_entity):
        """Test that switch has correct device info."""
        device_info = switch_entity.device_info
        assert device_info["name"] == "Test IHP"
        assert device_info["manufacturer"] == "Intelligent Heating Pilot"
        assert device_info["model"] == "Intelligent Preheating with ML"

    @pytest.mark.asyncio
    async def test_turn_on(self, switch_entity, mock_coordinator):
        """Test turning on the switch."""
        with patch.object(switch_entity, "async_write_ha_state") as mock_write:
            await switch_entity.async_turn_on()
            mock_coordinator.set_ihp_enabled.assert_called_once_with(True)
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, switch_entity, mock_coordinator):
        """Test turning off the switch."""
        with patch.object(switch_entity, "async_write_ha_state") as mock_write:
            await switch_entity.async_turn_off()
            mock_coordinator.set_ihp_enabled.assert_called_once_with(False)
            mock_write.assert_called_once()

    def test_is_on_reflects_coordinator_state(self, switch_entity, mock_coordinator):
        """Test that is_on property reflects coordinator state."""
        # Test when enabled
        mock_coordinator.is_ihp_enabled.return_value = True
        assert switch_entity.is_on is True

        # Test when disabled
        mock_coordinator.is_ihp_enabled.return_value = False
        assert switch_entity.is_on is False

    def test_extra_state_attributes(self, switch_entity):
        """Test that switch provides helpful description."""
        attrs = switch_entity.extra_state_attributes
        assert "description" in attrs
        assert "learning" in attrs["description"]
        assert "preheating" in attrs["description"]
