"""Tests for HAEnvironmentReader adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader import (
    HAEnvironmentReader,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.states.get = Mock()
    return hass


def _make_state(state_value: str | None = None, attributes: dict | None = None) -> Mock:
    state = Mock()
    state.state = state_value
    state.attributes = attributes or {}
    return state


@pytest.mark.asyncio
async def test_get_current_environment_returns_none_when_vtherm_missing(
    mock_hass: Mock,
) -> None:
    """Return None when the VTherm entity is missing."""
    mock_hass.states.get.return_value = None

    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.get_entity_name",
        return_value="Living Room",
    ):
        reader = HAEnvironmentReader(mock_hass, "climate.vtherm")
        result = await reader.get_current_environment()

    assert result is None


@pytest.mark.asyncio
async def test_get_current_environment_returns_none_when_current_temp_missing(
    mock_hass: Mock,
) -> None:
    """Return None when current temperature is not available."""
    vtherm_state = _make_state(attributes={})
    mock_hass.states.get.return_value = vtherm_state

    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.get_entity_name",
        return_value="Living Room",
    ):
        reader = HAEnvironmentReader(mock_hass, "climate.vtherm")
        result = await reader.get_current_environment()

    assert result is None


@pytest.mark.asyncio
async def test_get_current_environment_returns_none_when_current_temp_invalid(
    mock_hass: Mock,
) -> None:
    """Return None when current temperature cannot be parsed."""
    vtherm_state = _make_state(attributes={"current_temperature": "not-a-number"})
    mock_hass.states.get.return_value = vtherm_state

    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.get_entity_name",
        return_value="Living Room",
    ):
        reader = HAEnvironmentReader(mock_hass, "climate.vtherm")
        result = await reader.get_current_environment()

    assert result is None


@pytest.mark.asyncio
async def test_get_current_environment_uses_fallbacks_when_optional_missing(
    mock_hass: Mock,
) -> None:
    """Fallback to indoor temp and default humidity when optional sensors are missing."""
    vtherm_state = _make_state(attributes={"current_temperature": 21.5})

    def _get_state(entity_id: str) -> Mock | None:
        if entity_id == "climate.vtherm":
            return vtherm_state
        return None

    mock_hass.states.get.side_effect = _get_state
    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.get_entity_name",
            return_value="Living Room",
        ),
        patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.dt_util.now",
            return_value=fixed_now,
        ),
    ):
        reader = HAEnvironmentReader(
            mock_hass,
            "climate.vtherm",
            outdoor_temp_entity_id="sensor.outdoor_temp",
            humidity_in_entity_id="sensor.indoor_humidity",
        )
        result = await reader.get_current_environment()

    assert result is not None
    assert result.indoor_temperature == 21.5
    assert result.outdoor_temp == 21.5
    assert result.indoor_humidity == 50.0
    assert result.timestamp == fixed_now
    assert result.outdoor_humidity is None
    assert result.cloud_coverage is None


@pytest.mark.asyncio
async def test_get_current_environment_reads_optional_sensors(mock_hass: Mock) -> None:
    """Read optional sensors when configured and available."""
    vtherm_state = _make_state(attributes={"current_temperature": 20.0})
    outdoor_temp_state = _make_state(state_value="5.5")
    humidity_in_state = _make_state(state_value="45")
    humidity_out_state = _make_state(state_value="70")
    cloud_cover_state = _make_state(state_value="25")

    def _get_state(entity_id: str) -> Mock | None:
        mapping = {
            "climate.vtherm": vtherm_state,
            "sensor.outdoor_temp": outdoor_temp_state,
            "sensor.indoor_humidity": humidity_in_state,
            "sensor.outdoor_humidity": humidity_out_state,
            "sensor.cloud_cover": cloud_cover_state,
        }
        return mapping.get(entity_id)

    mock_hass.states.get.side_effect = _get_state
    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.get_entity_name",
            return_value="Living Room",
        ),
        patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader.dt_util.now",
            return_value=fixed_now,
        ),
    ):
        reader = HAEnvironmentReader(
            mock_hass,
            "climate.vtherm",
            outdoor_temp_entity_id="sensor.outdoor_temp",
            humidity_in_entity_id="sensor.indoor_humidity",
            humidity_out_entity_id="sensor.outdoor_humidity",
            cloud_cover_entity_id="sensor.cloud_cover",
        )
        result = await reader.get_current_environment()

    assert result is not None
    assert result.indoor_temperature == 20.0
    assert result.outdoor_temp == 5.5
    assert result.indoor_humidity == 45.0
    assert result.outdoor_humidity == 70.0
    assert result.cloud_coverage == 25.0
    assert result.timestamp == fixed_now
