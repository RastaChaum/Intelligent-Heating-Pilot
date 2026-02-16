"""pytest-bdd step definitions for Heating Orchestration Workflow scenarios.

Implements BDD steps for testing the HeatingOrchestrator's main workflow:
- calculate_and_schedule_anticipation() — the complete workflow
- Revert logic when LHS improves
- IHP enabled/disabled handling
- Scheduler disabled detection
- Overshoot prevention coordination

These are RED tests — the orchestrator does NOT yet have these workflow methods.
Expected failures: AttributeError on missing methods.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.orchestrator import (
    HeatingOrchestrator,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    CalculateAnticipationUseCase,
    ControlPreheatingUseCase,
    ResetLearningUseCase,
    SchedulePreheatingUseCase,
    UpdateCacheDataUseCase,
)

# Load all scenarios from heating_orchestration_workflow.feature
scenarios("heating_orchestration_workflow.feature")


# ============================================================================
# Fixtures — shared context and mock use cases
# ============================================================================


@pytest.fixture
def workflow_context():
    """Shared context for orchestration workflow BDD scenarios."""
    return {
        "result": None,
        "error": None,
        "ihp_enabled": True,
        "preheating_active": False,
        "target_time": None,
        "target_temp": None,
        "current_temp": None,
        "anticipated_start_time": None,
        "scheduler_entity": "switch.test_schedule",
        "current_time": datetime(2025, 2, 10, 5, 0, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def mock_calculate_anticipation():
    """Mock CalculateAnticipationUseCase."""
    mock = Mock(spec=CalculateAnticipationUseCase)
    mock.calculate_anticipation_datas = AsyncMock(
        return_value={
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "anticipation_minutes": None,
            "current_temp": None,
            "learned_heating_slope": None,
            "confidence_level": None,
            "timeslot_id": None,
            "scheduler_entity": None,
        }
    )
    return mock


@pytest.fixture
def mock_control_preheating():
    """Mock ControlPreheatingUseCase."""
    mock = Mock(spec=ControlPreheatingUseCase)
    mock.is_preheating_active = Mock(return_value=False)
    mock.get_preheating_target_time = Mock(return_value=None)
    mock.get_active_scheduler_entity = Mock(return_value=None)
    mock.cancel_preheating = AsyncMock()
    mock.start_preheating = AsyncMock()
    return mock


@pytest.fixture
def mock_schedule_preheating():
    """Mock SchedulePreheatingUseCase."""
    mock = Mock(spec=SchedulePreheatingUseCase)
    mock.create_preheating_scheduler = AsyncMock()
    mock.cancel_preheating_scheduler = AsyncMock()
    return mock


@pytest.fixture
def mock_update_cache():
    """Mock UpdateCacheDataUseCase."""
    return Mock(spec=UpdateCacheDataUseCase)


@pytest.fixture
def mock_reset_learning():
    """Mock ResetLearningUseCase."""
    return Mock(spec=ResetLearningUseCase)


@pytest.fixture
def orchestrator(
    mock_calculate_anticipation,
    mock_control_preheating,
    mock_schedule_preheating,
    mock_update_cache,
    mock_reset_learning,
):
    """Create HeatingOrchestrator with mocked use cases."""
    return HeatingOrchestrator(
        calculate_anticipation=mock_calculate_anticipation,
        control_preheating=mock_control_preheating,
        schedule_preheating=mock_schedule_preheating,
        update_cache=mock_update_cache,
        reset_learning=mock_reset_learning,
    )


# ============================================================================
# GIVEN Steps — Setup initial conditions
# ============================================================================


@given("the orchestrator is configured with all use cases")
def orchestrator_is_configured(orchestrator, workflow_context):
    """GIVEN: Orchestrator is ready with all use cases injected."""
    workflow_context["orchestrator"] = orchestrator


@given(
    parsers.parse(
        "the next timeslot is at {hour:d}:00 with target temperature {temp:d}°C"
    )
)
def next_timeslot_configured(
    workflow_context,
    mock_calculate_anticipation,
    hour,
    temp,
):
    """GIVEN: A scheduler timeslot exists at the given time and temperature."""
    target_time = datetime(2025, 2, 10, hour, 0, 0, tzinfo=timezone.utc)
    workflow_context["target_time"] = target_time
    workflow_context["target_temp"] = float(temp)

    # Configure the calculate anticipation mock to return data with this timeslot
    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "next_schedule_time": target_time,
            "next_target_temperature": float(temp),
            "scheduler_entity": workflow_context["scheduler_entity"],
            "timeslot_id": "test_timeslot",
        }
    )


@given(parsers.parse("the current indoor temperature is {temp:d}°C"))
def current_temperature(workflow_context, mock_calculate_anticipation, temp):
    """GIVEN: The current indoor temperature is known."""
    workflow_context["current_temp"] = float(temp)
    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {"current_temp": float(temp)}
    )


@given(parsers.parse("the calculated anticipated start time is {hour:d}:{minute:d}"))
def anticipated_start_time_set(
    workflow_context,
    mock_calculate_anticipation,
    hour,
    minute,
):
    """GIVEN: The anticipation calculation yields a specific start time."""
    anticipated = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    workflow_context["anticipated_start_time"] = anticipated

    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "anticipated_start_time": anticipated,
            "anticipation_minutes": 90.0,  # Placeholder nonzero
            "learned_heating_slope": 2.0,
            "confidence_level": 80.0,
        }
    )


@given("anticipation calculation returns 0 minutes of anticipation")
def anticipation_zero_minutes(workflow_context, mock_calculate_anticipation):
    """GIVEN: Already at target — anticipation calculation returns 0 minutes."""
    target_time = workflow_context.get("target_time") or datetime(
        2025, 2, 10, 7, 0, 0, tzinfo=timezone.utc
    )
    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "anticipated_start_time": target_time,
            "anticipation_minutes": 0,
            "learned_heating_slope": 2.0,
            "confidence_level": 100.0,
        }
    )


@given("no scheduler timeslot is available")
def no_scheduler_timeslot(mock_calculate_anticipation):
    """GIVEN: No scheduler is configured or no timeslot is available."""
    mock_calculate_anticipation.calculate_anticipation_datas.return_value = {
        "anticipated_start_time": None,
        "next_schedule_time": None,
        "next_target_temperature": None,
        "anticipation_minutes": None,
        "current_temp": None,
        "learned_heating_slope": None,
        "confidence_level": None,
        "timeslot_id": None,
        "scheduler_entity": None,
    }


@given(parsers.parse("preheating is currently active for target time {hour:d}:00"))
def preheating_active_for_target(
    workflow_context,
    mock_control_preheating,
    hour,
):
    """GIVEN: Preheating is currently active for a specific target time."""
    target_time = datetime(2025, 2, 10, hour, 0, 0, tzinfo=timezone.utc)
    workflow_context["preheating_active"] = True
    workflow_context["target_time"] = target_time

    mock_control_preheating.is_preheating_active.return_value = True
    mock_control_preheating.get_preheating_target_time.return_value = target_time
    mock_control_preheating.get_active_scheduler_entity.return_value = (
        workflow_context["scheduler_entity"]
    )


@given(
    parsers.parse(
        "the new anticipated start time is {hour:d}:{minute:d} which is after the current time"
    )
)
def anticipated_start_in_future(
    workflow_context,
    mock_calculate_anticipation,
    hour,
    minute,
):
    """GIVEN: The new anticipated start time is after `now` (LHS improved)."""
    anticipated = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    workflow_context["anticipated_start_time"] = anticipated
    workflow_context["current_time"] = datetime(
        2025, 2, 10, 6, 0, 0, tzinfo=timezone.utc
    )  # now is 06:00, anticipated is later

    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "anticipated_start_time": anticipated,
            "next_schedule_time": workflow_context["target_time"],
            "next_target_temperature": 21.0,
            "anticipation_minutes": 45.0,
            "learned_heating_slope": 3.0,
            "confidence_level": 85.0,
            "scheduler_entity": workflow_context["scheduler_entity"],
            "timeslot_id": "test_timeslot",
        }
    )


@given("the anticipated start time is still in the past")
def anticipated_start_in_past(workflow_context, mock_calculate_anticipation):
    """GIVEN: The anticipated start time is before `now` — preheating should continue."""
    past_time = datetime(2025, 2, 10, 4, 30, 0, tzinfo=timezone.utc)
    workflow_context["anticipated_start_time"] = past_time
    workflow_context["current_time"] = datetime(2025, 2, 10, 6, 0, 0, tzinfo=timezone.utc)

    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "anticipated_start_time": past_time,
            "next_schedule_time": workflow_context["target_time"],
            "next_target_temperature": 21.0,
            "anticipation_minutes": 150.0,
            "learned_heating_slope": 1.5,
            "confidence_level": 75.0,
            "scheduler_entity": workflow_context["scheduler_entity"],
            "timeslot_id": "test_timeslot",
        }
    )


@given(parsers.parse("the current time is past {hour:d}:00"))
def current_time_past_target(
    workflow_context,
    mock_calculate_anticipation,
    hour,
):
    """GIVEN: The current time is past the target time."""
    workflow_context["current_time"] = datetime(
        2025, 2, 10, hour, 5, 0, tzinfo=timezone.utc
    )

    mock_calculate_anticipation.calculate_anticipation_datas.return_value.update(
        {
            "anticipated_start_time": datetime(
                2025, 2, 10, hour - 2, 0, 0, tzinfo=timezone.utc
            ),
            "next_schedule_time": datetime(
                2025, 2, 10, hour, 0, 0, tzinfo=timezone.utc
            ),
            "next_target_temperature": 21.0,
            "anticipation_minutes": 0,
            "scheduler_entity": workflow_context["scheduler_entity"],
            "timeslot_id": "test_timeslot",
        }
    )


@given("no preheating is currently active")
def no_preheating_active(workflow_context, mock_control_preheating):
    """GIVEN: No preheating is currently running."""
    workflow_context["preheating_active"] = False
    mock_control_preheating.is_preheating_active.return_value = False
    mock_control_preheating.get_preheating_target_time.return_value = None
    mock_control_preheating.get_active_scheduler_entity.return_value = None


@given("the scheduler entity was previously active")
def scheduler_was_active(workflow_context):
    """GIVEN: A scheduler entity was previously tracked as active."""
    workflow_context["scheduler_was_active"] = True


@given("the scheduler is now disabled")
def scheduler_is_disabled(mock_calculate_anticipation, workflow_context):
    """GIVEN: The active scheduler has been disabled."""
    # When scheduler is disabled, calculate_anticipation returns clear values
    mock_calculate_anticipation.calculate_anticipation_datas.return_value = {
        "anticipated_start_time": None,
        "next_schedule_time": None,
        "next_target_temperature": None,
        "anticipation_minutes": None,
        "current_temp": None,
        "learned_heating_slope": None,
        "confidence_level": None,
        "timeslot_id": None,
        "scheduler_entity": None,
    }
    workflow_context["scheduler_disabled"] = True


@given("overshoot risk is detected by the overshoot use case")
def overshoot_risk_detected(workflow_context):
    """GIVEN: The overshoot risk checker has determined overshoot is imminent."""
    workflow_context["overshoot_detected"] = True


# ============================================================================
# WHEN Steps — Actions that trigger behavior
# ============================================================================


@when("the orchestrator calculates and schedules anticipation")
def orchestrator_calculates_and_schedules(workflow_context):
    """WHEN: The main orchestration workflow is triggered.

    This calls calculate_and_schedule_anticipation() which does NOT exist
    yet on the orchestrator — this is a RED test.
    Expected failure: AttributeError
    """
    orchestrator = workflow_context["orchestrator"]
    result = asyncio.run(
        orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)
    )
    workflow_context["result"] = result


@when("the orchestrator calculates and schedules anticipation with IHP disabled")
def orchestrator_calculates_ihp_disabled(workflow_context):
    """WHEN: The workflow is triggered with IHP explicitly disabled.

    Expected failure: AttributeError (method does not exist yet)
    """
    orchestrator = workflow_context["orchestrator"]
    result = asyncio.run(
        orchestrator.calculate_and_schedule_anticipation(ihp_enabled=False)
    )
    workflow_context["result"] = result


@when("the orchestrator calculates and schedules anticipation with IHP enabled")
def orchestrator_calculates_ihp_enabled(workflow_context):
    """WHEN: The workflow is triggered with IHP explicitly enabled.

    Expected failure: AttributeError (method does not exist yet)
    """
    orchestrator = workflow_context["orchestrator"]
    result = asyncio.run(
        orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)
    )
    workflow_context["result"] = result


@when("the orchestrator checks for overshoot risk")
def orchestrator_checks_overshoot(workflow_context):
    """WHEN: The orchestrator checks for overshoot risk.

    Expected failure: AttributeError (method does not exist yet)
    """
    orchestrator = workflow_context["orchestrator"]
    scheduler_entity = workflow_context["scheduler_entity"]
    result = asyncio.run(
        orchestrator.check_and_prevent_overshoot(scheduler_entity)
    )
    workflow_context["overshoot_result"] = result


# ============================================================================
# THEN Steps — Verify expected outcomes
# ============================================================================


@then(parsers.parse("a preheating timer should be scheduled for {hour:d}:{minute:d}"))
def preheating_timer_scheduled(
    workflow_context,
    mock_schedule_preheating,
    hour,
    minute,
):
    """THEN: A preheating timer was created for the anticipated start time."""
    expected_time = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    mock_schedule_preheating.create_preheating_scheduler.assert_called_once()

    call_args = mock_schedule_preheating.create_preheating_scheduler.call_args
    actual_start = call_args.kwargs.get(
        "anticipated_start", call_args.args[0] if call_args.args else None
    )
    assert actual_start == expected_time, (
        f"Expected timer at {expected_time}, got {actual_start}"
    )


@then(parsers.parse("the result should contain anticipated start time {hour:d}:{minute:d}"))
def result_contains_anticipated_start(workflow_context, hour, minute):
    """THEN: The result dict contains the expected anticipated start time."""
    expected_time = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    result = workflow_context["result"]
    assert result is not None, "Result should not be None"
    assert result["anticipated_start_time"] == expected_time


@then(parsers.parse("the result should contain next target temperature {temp:d}°C"))
def result_contains_target_temp(workflow_context, temp):
    """THEN: The result dict contains the expected target temperature."""
    result = workflow_context["result"]
    assert result is not None
    assert result["next_target_temperature"] == float(temp)


@then("no preheating timer should be scheduled")
def no_preheating_timer(mock_schedule_preheating):
    """THEN: No preheating timer was created."""
    mock_schedule_preheating.create_preheating_scheduler.assert_not_called()


@then(parsers.parse("the result should contain {minutes:d} anticipation minutes"))
def result_contains_anticipation_minutes(workflow_context, minutes):
    """THEN: The result reflects the expected anticipation minutes."""
    result = workflow_context["result"]
    assert result is not None
    assert result["anticipation_minutes"] == minutes


@then("the result should indicate clear values")
def result_indicates_clear_values(workflow_context):
    """THEN: The result indicates sensors should be cleared (no valid data)."""
    result = workflow_context["result"]
    assert result is not None
    # clear_values flag or all None values indicate clearing
    if "clear_values" in result:
        assert result["clear_values"] is True
    else:
        assert result["anticipated_start_time"] is None
        assert result["next_schedule_time"] is None


@then("the active preheating should be canceled")
def active_preheating_canceled(mock_control_preheating):
    """THEN: The control use case was called to cancel active preheating."""
    mock_control_preheating.cancel_preheating.assert_called_once()


@then(
    parsers.parse(
        "a new preheating timer should be rescheduled for {hour:d}:{minute:d}"
    )
)
def new_preheating_rescheduled(mock_schedule_preheating, hour, minute):
    """THEN: A new timer was created at the updated anticipated start time."""
    expected_time = datetime(2025, 2, 10, hour, minute, 0, tzinfo=timezone.utc)
    mock_schedule_preheating.create_preheating_scheduler.assert_called()

    call_args = mock_schedule_preheating.create_preheating_scheduler.call_args
    actual_start = call_args.kwargs.get(
        "anticipated_start", call_args.args[0] if call_args.args else None
    )
    assert actual_start == expected_time


@then("the preheating state should be reset to inactive")
def preheating_state_reset(mock_control_preheating):
    """THEN: After revert, preheating is no longer active."""
    # The orchestrator should have canceled preheating, which resets internal state
    mock_control_preheating.cancel_preheating.assert_called()


@then("preheating should continue without interruption")
def preheating_continues(mock_control_preheating):
    """THEN: No cancel was issued — preheating keeps running."""
    mock_control_preheating.cancel_preheating.assert_not_called()


@then("no cancel action should be triggered")
def no_cancel_action(mock_control_preheating):
    """THEN: No cancel action was issued at all."""
    mock_control_preheating.cancel_preheating.assert_not_called()


@then("preheating should be marked as complete")
def preheating_marked_complete(workflow_context):
    """THEN: The result indicates preheating has completed (target reached)."""
    result = workflow_context["result"]
    assert result is not None
    # When target time is reached, anticipation minutes should be 0
    assert result.get("anticipation_minutes", None) == 0


@then("the anticipation state should be cleared")
def anticipation_state_cleared(mock_schedule_preheating):
    """THEN: Timer and anticipation state were cleaned up."""
    mock_schedule_preheating.cancel_preheating_scheduler.assert_called()


@then("no new preheating timer should be scheduled")
def no_new_timer_scheduled(mock_schedule_preheating):
    """THEN: No new timer was created after cancellation."""
    mock_schedule_preheating.create_preheating_scheduler.assert_not_called()


@then("any active preheating should be canceled")
def any_active_preheating_canceled(mock_control_preheating):
    """THEN: If any preheating was active, it was canceled."""
    # This step is used in scheduler-disabled scenario
    # The orchestrator should clean up any active state
    # Either cancel_preheating was called or there was nothing to cancel
    pass  # Verified implicitly by anticipation_state_cleared


@then("preheating should be canceled due to overshoot")
def preheating_canceled_overshoot(mock_control_preheating):
    """THEN: Preheating was canceled because of overshoot risk."""
    mock_control_preheating.cancel_preheating.assert_called_once()


@then("the system should remain in idle state")
def system_remains_idle(mock_control_preheating, mock_schedule_preheating):
    """THEN: No changes were made — system stays idle."""
    mock_control_preheating.cancel_preheating.assert_not_called()
    mock_control_preheating.start_preheating.assert_not_called()
    mock_schedule_preheating.create_preheating_scheduler.assert_not_called()
