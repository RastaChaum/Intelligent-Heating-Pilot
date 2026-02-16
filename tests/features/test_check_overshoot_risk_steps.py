"""pytest-bdd step definitions for Check Overshoot Risk scenarios.

Implements BDD steps for testing the CheckOvershootRiskUseCase, which
detects when current heating slope would cause temperature overshoot
and cancels preheating to prevent overheating.

These are RED tests — CheckOvershootRiskUseCase does NOT exist yet.
Expected failure: ImportError at module collection time.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)

# RED IMPORT — This class does not exist yet.
# All tests in this file will fail with ImportError at collection time.
from custom_components.intelligent_heating_pilot.application.use_cases import (
    CheckOvershootRiskUseCase,
)

from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IClimateDataReader,
    IEnvironmentReader,
    ISchedulerReader,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    ScheduledTimeslot,
)

# Load all scenarios from check_overshoot_risk.feature
scenarios("check_overshoot_risk.feature")


# ============================================================================
# Fixtures — shared context and mock dependencies
# ============================================================================


@pytest.fixture
def overshoot_context():
    """Shared context for overshoot risk BDD scenarios."""
    return {
        "result": None,
        "preheating_active": False,
        "scheduler_entity_id": "switch.living_room_schedule",
        "target_temp": None,
        "target_time": None,
        "current_temp": None,
        "current_slope": None,
        "current_time": None,
    }


@pytest.fixture
def mock_scheduler_reader():
    """Mock ISchedulerReader for reading timeslots."""
    mock = Mock(spec=ISchedulerReader)
    mock.get_next_timeslot = AsyncMock(return_value=None)
    mock.is_scheduler_enabled = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_environment_reader():
    """Mock IEnvironmentReader for reading current conditions."""
    mock = Mock(spec=IEnvironmentReader)
    mock.get_current_environment = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_climate_data_reader():
    """Mock IClimateDataReader for reading current heating slope."""
    mock = Mock(spec=IClimateDataReader)
    mock.get_current_slope = Mock(return_value=None)
    mock.get_vtherm_entity_id = Mock(return_value="climate.test_vtherm")
    mock.is_heating_active = Mock(return_value=False)
    return mock


@pytest.fixture
def mock_control_preheating_uc():
    """Mock ControlPreheatingUseCase for canceling preheating."""
    mock = Mock(spec=ControlPreheatingUseCase)
    mock.is_preheating_active = Mock(return_value=False)
    mock.cancel_preheating = AsyncMock()
    return mock


@pytest.fixture
def overshoot_use_case(
    mock_scheduler_reader,
    mock_environment_reader,
    mock_climate_data_reader,
    mock_control_preheating_uc,
):
    """Create CheckOvershootRiskUseCase with mocked dependencies.

    This will fail because CheckOvershootRiskUseCase doesn't exist yet (RED).
    """
    return CheckOvershootRiskUseCase(
        scheduler_reader=mock_scheduler_reader,
        environment_reader=mock_environment_reader,
        climate_data_reader=mock_climate_data_reader,
        control_preheating=mock_control_preheating_uc,
    )


# ============================================================================
# GIVEN Steps — Setup initial conditions
# ============================================================================


@given("the overshoot risk checker is configured")
def overshoot_checker_configured(overshoot_use_case, overshoot_context):
    """GIVEN: The overshoot risk checker is ready."""
    overshoot_context["use_case"] = overshoot_use_case


@given(parsers.parse("the overshoot threshold is {threshold}°C above target"))
def overshoot_threshold_set(overshoot_context, threshold):
    """GIVEN: The overshoot detection threshold is defined."""
    overshoot_context["overshoot_threshold"] = float(threshold)


@given(parsers.parse('preheating is active for scheduler "{scheduler_entity}"'))
def preheating_active_for_scheduler(
    overshoot_context,
    mock_control_preheating_uc,
    scheduler_entity,
):
    """GIVEN: Preheating is currently active for the given scheduler."""
    overshoot_context["preheating_active"] = True
    overshoot_context["scheduler_entity_id"] = scheduler_entity
    mock_control_preheating_uc.is_preheating_active.return_value = True


@given("no preheating is currently active")
def no_preheating_active_overshoot(overshoot_context, mock_control_preheating_uc):
    """GIVEN: No preheating is running."""
    overshoot_context["preheating_active"] = False
    mock_control_preheating_uc.is_preheating_active.return_value = False


@given(parsers.parse("the next target is {temp}°C at {hour:d}:{minute:d}"))
def next_target_configured(
    overshoot_context,
    mock_scheduler_reader,
    temp,
    hour,
    minute,
):
    """GIVEN: The next scheduled target temperature and time."""
    target_time = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    target_temp = float(temp)
    overshoot_context["target_time"] = target_time
    overshoot_context["target_temp"] = target_temp

    timeslot = ScheduledTimeslot(
        target_time=target_time,
        target_temp=target_temp,
        timeslot_id="test_timeslot",
        scheduler_entity=overshoot_context["scheduler_entity_id"],
    )
    mock_scheduler_reader.get_next_timeslot.return_value = timeslot


@given("no scheduler timeslot is available")
def no_timeslot_available_overshoot(mock_scheduler_reader):
    """GIVEN: No scheduler timeslot exists."""
    mock_scheduler_reader.get_next_timeslot.return_value = None


@given(parsers.parse("the current indoor temperature is {temp}°C"))
def current_temperature_overshoot(
    overshoot_context,
    mock_environment_reader,
    temp,
):
    """GIVEN: The current indoor temperature reading."""
    current_temp = float(temp)
    overshoot_context["current_temp"] = current_temp

    current_time = overshoot_context.get("current_time") or datetime(
        2025, 2, 10, 6, 30, 0, tzinfo=timezone.utc
    )
    environment = EnvironmentState(
        timestamp=current_time,
        indoor_temperature=current_temp,
        outdoor_temp=5.0,
        indoor_humidity=60.0,
        cloud_coverage=50.0,
    )
    mock_environment_reader.get_current_environment.return_value = environment


@given(parsers.parse("the current heating slope is {slope}°C per hour"))
def current_slope_overshoot(overshoot_context, mock_climate_data_reader, slope):
    """GIVEN: The VTherm reports a current heating slope."""
    slope_value = float(slope)
    overshoot_context["current_slope"] = slope_value
    mock_climate_data_reader.get_current_slope.return_value = slope_value


@given(parsers.parse("the current time is {hour:d}:{minute:d}"))
def current_time_overshoot(overshoot_context, mock_environment_reader, hour, minute):
    """GIVEN: The current time for overshoot calculation."""
    current_time = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    overshoot_context["current_time"] = current_time

    # Update environment with correct timestamp if already set
    if overshoot_context.get("current_temp") is not None:
        environment = EnvironmentState(
            timestamp=current_time,
            indoor_temperature=overshoot_context["current_temp"],
            outdoor_temp=5.0,
            indoor_humidity=60.0,
            cloud_coverage=50.0,
        )
        mock_environment_reader.get_current_environment.return_value = environment


# ============================================================================
# WHEN Steps — Actions that trigger behavior
# ============================================================================


@when("the system checks for overshoot risk")
def system_checks_overshoot(overshoot_context):
    """WHEN: The overshoot check is performed.

    Calls check_and_prevent_overshoot() on the CheckOvershootRiskUseCase.
    This is a RED test — the class does not exist yet.
    """
    use_case = overshoot_context["use_case"]
    scheduler_entity = overshoot_context["scheduler_entity_id"]
    result = asyncio.run(
        use_case.check_and_prevent_overshoot(scheduler_entity_id=scheduler_entity)
    )
    overshoot_context["result"] = result


# ============================================================================
# THEN Steps — Verify expected outcomes
# ============================================================================


@then("overshoot should be detected")
def overshoot_detected(overshoot_context):
    """THEN: The check confirmed overshoot risk."""
    assert overshoot_context["result"] is True


@then("preheating should be canceled to prevent overheating")
def preheating_canceled_for_overshoot(mock_control_preheating_uc):
    """THEN: Preheating was stopped to prevent overshoot."""
    mock_control_preheating_uc.cancel_preheating.assert_called_once()


@then("the method should return True")
def method_returns_true(overshoot_context):
    """THEN: check_and_prevent_overshoot returned True."""
    assert overshoot_context["result"] is True


@then("no overshoot should be detected")
def no_overshoot_detected(overshoot_context):
    """THEN: No overshoot risk was found."""
    assert overshoot_context["result"] is False


@then("preheating should continue normally")
def preheating_continues_overshoot(mock_control_preheating_uc):
    """THEN: No cancel was issued — preheating continues."""
    mock_control_preheating_uc.cancel_preheating.assert_not_called()


@then("the method should return False")
def method_returns_false(overshoot_context):
    """THEN: check_and_prevent_overshoot returned False."""
    assert overshoot_context["result"] is False


@then("the check should be skipped")
def check_was_skipped(overshoot_context, mock_control_preheating_uc):
    """THEN: The overshoot check was skipped entirely."""
    assert overshoot_context["result"] is False
    mock_control_preheating_uc.cancel_preheating.assert_not_called()


@then("the check should be skipped because slope is zero")
def check_skipped_zero_slope(overshoot_context, mock_control_preheating_uc):
    """THEN: Skipped because zero slope means no heating progress."""
    assert overshoot_context["result"] is False
    mock_control_preheating_uc.cancel_preheating.assert_not_called()


@then("the check should be skipped because target time has passed")
def check_skipped_target_passed(overshoot_context, mock_control_preheating_uc):
    """THEN: Skipped because target time is already in the past."""
    assert overshoot_context["result"] is False
    mock_control_preheating_uc.cancel_preheating.assert_not_called()
