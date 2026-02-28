"""Tests for HAContextReader adapter."""

from __future__ import annotations

from unittest.mock import Mock

from custom_components.intelligent_heating_pilot.infrastructure.adapters.context_reader import (
    HAContextReader,
)


def test_context_reader_returns_hass_instance() -> None:
    """Return the Home Assistant instance."""
    mock_hass = Mock()
    reader = HAContextReader(mock_hass)

    assert reader.get_hass() is mock_hass


def test_context_reader_returns_entity_ids() -> None:
    """Return configured entity IDs for optional sensors."""
    mock_hass = Mock()
    reader = HAContextReader(
        mock_hass,
        outdoor_temp_entity_id="sensor.outdoor_temp",
        humidity_in_entity_id="sensor.indoor_humidity",
        humidity_out_entity_id="sensor.outdoor_humidity",
        cloud_cover_entity_id="sensor.cloud_cover",
    )

    assert reader.get_outdoor_temp_entity_id() == "sensor.outdoor_temp"
    assert reader.get_humidity_in_entity_id() == "sensor.indoor_humidity"
    assert reader.get_humidity_out_entity_id() == "sensor.outdoor_humidity"
    assert reader.get_cloud_cover_entity_id() == "sensor.cloud_cover"
