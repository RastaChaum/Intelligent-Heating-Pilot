"""Tests for HAClimateCommander adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander import (
    HAClimateCommander,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance with services."""
    hass = Mock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_set_temperature_calls_climate_service(mock_hass: Mock) -> None:
    """Call climate.set_temperature with expected parameters."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander.get_entity_name",
        return_value="Living Room",
    ):
        commander = HAClimateCommander(mock_hass, "climate.vtherm")
        await commander.set_temperature(21.5)

    mock_hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.vtherm", "temperature": 21.5},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_set_hvac_mode_calls_climate_service(mock_hass: Mock) -> None:
    """Call climate.set_hvac_mode with expected parameters."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander.get_entity_name",
        return_value="Living Room",
    ):
        commander = HAClimateCommander(mock_hass, "climate.vtherm")
        await commander.set_hvac_mode("heat")

    mock_hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.vtherm", "hvac_mode": "heat"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_uses_set_hvac_mode(mock_hass: Mock) -> None:
    """Turn off uses set_hvac_mode with 'off'."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander.get_entity_name",
        return_value="Living Room",
    ):
        commander = HAClimateCommander(mock_hass, "climate.vtherm")

    commander.set_hvac_mode = AsyncMock()

    await commander.turn_off()

    commander.set_hvac_mode.assert_awaited_once_with("off")


@pytest.mark.asyncio
async def test_turn_on_heat_sets_mode_and_temperature(mock_hass: Mock) -> None:
    """Turn on heat sets HVAC mode then temperature."""
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander.get_entity_name",
        return_value="Living Room",
    ):
        commander = HAClimateCommander(mock_hass, "climate.vtherm")

    commander.set_hvac_mode = AsyncMock()
    commander.set_temperature = AsyncMock()

    await commander.turn_on_heat(22.0)

    commander.set_hvac_mode.assert_awaited_once_with("heat")
    commander.set_temperature.assert_awaited_once_with(22.0)
