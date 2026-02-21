"""Unit tests for prediction confidence sensor normalization."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.sensor import (
    IntelligentHeatingPilotPredictionConfidenceSensor,
)


@pytest.fixture
def mock_config_entry() -> Mock:
    """Create a mock config entry."""
    config_entry = Mock()
    config_entry.entry_id = "test_entry_123"
    config_entry.data = {"name": "Test IHP"}
    return config_entry


@pytest.fixture
def mock_coordinator() -> Mock:
    """Create a mock coordinator for testing."""
    return Mock()


@pytest.fixture
def confidence_sensor(
    mock_coordinator: Mock,
    mock_config_entry: Mock,
) -> IntelligentHeatingPilotPredictionConfidenceSensor:
    """Create prediction confidence sensor instance."""
    return IntelligentHeatingPilotPredictionConfidenceSensor(
        coordinator=mock_coordinator,
        config_entry=mock_config_entry,
        name="Test IHP",
    )


class TestPredictionConfidenceSensor:
    """Regression tests for confidence scaling."""

    def test_confidence_from_ratio(
        self, confidence_sensor: IntelligentHeatingPilotPredictionConfidenceSensor
    ) -> None:
        """Ensure 0-1 confidence is displayed as 0-100%."""
        confidence_sensor._handle_anticipation_result({"confidence_level": 0.85})
        assert confidence_sensor.native_value == 85.0

    def test_confidence_from_percent(
        self, confidence_sensor: IntelligentHeatingPilotPredictionConfidenceSensor
    ) -> None:
        """Ensure 0-100 confidence is not double-scaled."""
        confidence_sensor._handle_anticipation_result({"confidence_level": 85.0})
        assert confidence_sensor.native_value == 85.0

    def test_none_confidence_resets_state(
        self, confidence_sensor: IntelligentHeatingPilotPredictionConfidenceSensor
    ) -> None:
        """Ensure None confidence_level resets sensor state."""
        confidence_sensor._handle_anticipation_result({"confidence_level": 0.5})
        assert confidence_sensor.native_value == 50.0

        confidence_sensor._handle_anticipation_result({"confidence_level": None})
        assert confidence_sensor.native_value is None
