"""Tests for domain value objects."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HeatingAction,
    HeatingDecision,
    PredictionResult,
    ScheduledTimeslot,
)
from tests.unit.domain.fixtures import (
    TEST_CURRENT_TEMP,
    TEST_HUMIDITY,
    TEST_OUTDOOR_TEMP,
    get_test_datetime,
)

# ============================================================================
# EnvironmentState Tests
# ============================================================================


def test_environment_state_creation() -> None:
    """Test creating a valid environment state."""
    now = get_test_datetime()
    state = EnvironmentState(
        indoor_temperature=TEST_CURRENT_TEMP,
        outdoor_temp=TEST_OUTDOOR_TEMP,
        indoor_humidity=TEST_HUMIDITY,
        timestamp=now,
    )

    assert state.indoor_temperature == TEST_CURRENT_TEMP
    assert state.outdoor_temp == TEST_OUTDOOR_TEMP
    assert state.indoor_humidity == TEST_HUMIDITY
    assert state.timestamp == now


def test_environment_state_with_optional_fields() -> None:
    """Test environment state with optional fields."""
    now = datetime.now(timezone.utc)
    state = EnvironmentState(
        indoor_temperature=20.0,
        outdoor_temp=10.0,
        indoor_humidity=50.0,
        timestamp=now,
        outdoor_humidity=60.0,
        cloud_coverage=75.0,
    )

    assert state.outdoor_humidity == 60.0
    assert state.cloud_coverage == 75.0


def test_environment_state_humidity_validation() -> None:
    """Test that humidity must be between 0 and 100."""
    now = datetime.now(timezone.utc)

    # Humidity too high
    with pytest.raises(ValueError):
        EnvironmentState(
            indoor_temperature=20.0,
            outdoor_temp=10.0,
            indoor_humidity=150.0,
            timestamp=now,
        )

    # Humidity too low
    with pytest.raises(ValueError):
        EnvironmentState(
            indoor_temperature=20.0,
            outdoor_temp=10.0,
            indoor_humidity=-10.0,
            timestamp=now,
        )


# ============================================================================
# ScheduledTimeslot Tests
# ============================================================================


def test_scheduled_timeslot_creation() -> None:
    """Test creating a valid scheduled timeslot."""
    target_time = datetime.now(timezone.utc)
    event = ScheduledTimeslot(
        target_time=target_time,
        target_temp=21.0,
        timeslot_id="test_event_1",
    )

    assert event.target_time == target_time
    assert event.target_temp == 21.0
    assert event.timeslot_id == "test_event_1"


def test_scheduled_timeslot_requires_id() -> None:
    """Test that timeslot_id cannot be empty."""
    target_time = datetime.now(timezone.utc)

    with pytest.raises(ValueError):
        ScheduledTimeslot(
            target_time=target_time,
            target_temp=21.0,
            timeslot_id="",
        )


# ============================================================================
# PredictionResult Tests
# ============================================================================


def test_prediction_result_creation() -> None:
    """Test creating a valid prediction result."""
    start_time = datetime.now(timezone.utc)
    result = PredictionResult(
        anticipated_start_time=start_time,
        estimated_duration_minutes=90.0,
        confidence_level=0.85,
        learned_heating_slope=2.0,
    )

    assert result.anticipated_start_time == start_time
    assert result.estimated_duration_minutes == 90.0
    assert result.confidence_level == 0.85
    assert result.learned_heating_slope == 2.0


def test_prediction_result_validation() -> None:
    """Test prediction result validation."""
    start_time = datetime.now(timezone.utc)

    # Negative duration
    with pytest.raises(ValueError):
        PredictionResult(
            anticipated_start_time=start_time,
            estimated_duration_minutes=-10.0,
            confidence_level=0.85,
            learned_heating_slope=2.0,
        )

    # Invalid confidence (> 1.0)
    with pytest.raises(ValueError):
        PredictionResult(
            anticipated_start_time=start_time,
            estimated_duration_minutes=90.0,
            confidence_level=1.5,
            learned_heating_slope=2.0,
        )

    # Invalid slope (zero)
    with pytest.raises(ValueError):
        PredictionResult(
            anticipated_start_time=start_time,
            estimated_duration_minutes=90.0,
            confidence_level=0.85,
            learned_heating_slope=0.0,
        )


# ============================================================================
# HeatingDecision Tests
# ============================================================================


def test_heating_decision_start_heating() -> None:
    """Test creating a START_HEATING decision."""
    decision = HeatingDecision(
        action=HeatingAction.START_HEATING,
        target_temp=21.0,
        reason="Time to start heating",
    )

    assert decision.action == HeatingAction.START_HEATING
    assert decision.target_temp == 21.0
    assert decision.reason == "Time to start heating"


def test_heating_decision_start_requires_target_temp() -> None:
    """Test that START_HEATING requires a target temperature."""
    with pytest.raises(ValueError):
        HeatingDecision(
            action=HeatingAction.START_HEATING,
            target_temp=None,
            reason="Time to start heating",
        )


def test_heating_decision_no_action() -> None:
    """Test creating a NO_ACTION decision."""
    decision = HeatingDecision(
        action=HeatingAction.NO_ACTION,
        reason="Already at target temperature",
    )

    assert decision.action == HeatingAction.NO_ACTION
    assert decision.target_temp is None
    assert decision.reason == "Already at target temperature"
