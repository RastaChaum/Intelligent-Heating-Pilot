"""Unit tests for IntelligentHeatingPilotContextualLearnedSlopeSensor (issue #226).

The sensor must show unknown (None) whenever the coordinator has no learned
contextual value for the scheduled hour, and must display any learned value,
including one equal to the default slope.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.const import ATTR_NEXT_SCHEDULE_TIME
from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_LEARNED_SLOPE,
)
from custom_components.intelligent_heating_pilot.sensor import (
    IntelligentHeatingPilotContextualLearnedSlopeSensor,
)

SCHEDULE_HOUR = 23
NEXT_SCHEDULE_TIME = datetime(2026, 1, 15, SCHEDULE_HOUR, 0)
LEARNED_CONTEXTUAL_LHS = 1.234
ROUNDED_CONTEXTUAL_LHS = 1.23


@pytest.fixture
def mock_coordinator() -> Mock:
    """Create a coordinator mock exposing the contextual LHS accessor."""
    coordinator = Mock()
    coordinator.get_contextual_learned_heating_slope = Mock(return_value=None)
    return coordinator


@pytest.fixture
def contextual_sensor(
    mock_coordinator: Mock,
) -> IntelligentHeatingPilotContextualLearnedSlopeSensor:
    """Create a contextual LHS sensor with a next schedule time set."""
    config_entry = Mock()
    config_entry.entry_id = "test_entry_contextual_lhs"
    sensor = IntelligentHeatingPilotContextualLearnedSlopeSensor(
        coordinator=mock_coordinator, config_entry=config_entry, name="Test IHP"
    )
    sensor._next_schedule_time = NEXT_SCHEDULE_TIME
    return sensor


class TestContextualLearnedSlopeSensorNativeValue:
    """native_value reflects only learned contextual values."""

    def test_unknown_when_hour_has_no_learned_value(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """No learned value for the scheduled hour: the sensor is unknown."""
        assert contextual_sensor.native_value is None
        mock_coordinator.get_contextual_learned_heating_slope.assert_called_once_with(SCHEDULE_HOUR)

    def test_shows_rounded_learned_value(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """A learned value is displayed rounded to two decimals."""
        mock_coordinator.get_contextual_learned_heating_slope.return_value = LEARNED_CONTEXTUAL_LHS

        assert contextual_sensor.native_value == ROUNDED_CONTEXTUAL_LHS

    def test_shows_learned_value_equal_to_default_slope(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """A learned value equal to the default slope is still a learned value."""
        mock_coordinator.get_contextual_learned_heating_slope.return_value = DEFAULT_LEARNED_SLOPE

        assert contextual_sensor.native_value == DEFAULT_LEARNED_SLOPE

    def test_unknown_without_next_schedule_time(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """Without a scheduled event there is no hour to look up."""
        contextual_sensor._next_schedule_time = None

        assert contextual_sensor.native_value is None
        mock_coordinator.get_contextual_learned_heating_slope.assert_not_called()


SLOT_AFTER_HALF_HOUR = datetime(2026, 1, 15, 6, 45)
NEAREST_HOUR_OF_SLOT = 7


class TestContextualLearnedSlopeSensorNearestHour:
    """The sensor shows the contextual hour of the next slot, the hour nearest to it (#214)."""

    def test_slot_after_half_hour_shows_slope_of_next_hour(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """A 06:45 slot uses the slope of 07:00, so the sensor shows it."""
        contextual_sensor._next_schedule_time = SLOT_AFTER_HALF_HOUR
        mock_coordinator.get_contextual_learned_heating_slope.return_value = LEARNED_CONTEXTUAL_LHS

        assert contextual_sensor.native_value == ROUNDED_CONTEXTUAL_LHS
        mock_coordinator.get_contextual_learned_heating_slope.assert_called_once_with(
            NEAREST_HOUR_OF_SLOT
        )

    def test_scheduled_hour_attribute_is_the_contextual_hour(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
    ) -> None:
        """The attribute names the hour whose slope is shown."""
        contextual_sensor._next_schedule_time = SLOT_AFTER_HALF_HOUR

        assert contextual_sensor.extra_state_attributes["scheduled_hour"] == "07:00"

    def test_state_is_written_when_the_contextual_hour_changes(
        self,
        contextual_sensor: IntelligentHeatingPilotContextualLearnedSlopeSensor,
        mock_coordinator: Mock,
    ) -> None:
        """06:20 and 06:40 share the clock hour but not the contextual hour."""
        contextual_sensor._next_schedule_time = datetime(2026, 1, 15, 6, 20)
        contextual_sensor._last_contextual_lhs_displayed = None
        contextual_sensor.async_write_ha_state = Mock()  # type: ignore[method-assign]

        contextual_sensor._handle_anticipation_result(
            {ATTR_NEXT_SCHEDULE_TIME: datetime(2026, 1, 15, 6, 40)}
        )

        contextual_sensor.async_write_ha_state.assert_called_once()
