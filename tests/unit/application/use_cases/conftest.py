"""Fixtures for use case testing.

Creates HomeAssistant mock and real adapter instances for integration testing.
Tests the real use case logic with real adapters mocking only HA.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    CheckOvershootRiskUseCase,
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    ScheduledTimeslot,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HAClimateDataReader,
    HAEnvironmentReader,
    HASchedulerCommander,
    HASchedulerReader,
)

# ============================================================================
# Home Assistant Mock
# ============================================================================


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance for testing.

    Provides:
    - states: A dict-like object to mock entity states
    - is_running: Property for HA status
    - services: For scheduler commands
    """
    hass = Mock()

    # Mock states system
    hass.states.get = Mock(return_value=None)

    # Mock services system
    hass.services.async_call = AsyncMock()

    # HA is running
    hass.is_running = True

    return hass


@pytest.fixture
def ha_state_builder(mock_hass: Mock):
    """Helper to set state values in mock HA.

    Usage:
        ha_state_builder.set_state(
            "sensor.temperature",
            "20.5",
            {"unit_of_measurement": "°C"}
        )
    """

    class StateBuilder:
        def __init__(self, hass: Mock):
            self._hass = hass
            self._states: dict[str, dict] = {}

        def set_state(
            self,
            entity_id: str,
            state: str,
            attributes: dict | None = None,
        ) -> None:
            """Set entity state in mock HA."""
            state_obj = Mock()
            state_obj.state = state
            state_obj.attributes = attributes or {}
            state_obj.entity_id = entity_id

            self._states[entity_id] = state_obj

            # Update the mock to return this state
            def get_state(eid: str):
                return self._states.get(eid)

            self._hass.states.get = Mock(side_effect=get_state)

        def get_state(self, entity_id: str) -> Mock | None:
            """Get current state from builder."""
            return self._states.get(entity_id)

    return StateBuilder(mock_hass)


# ============================================================================
# Adapter Fixtures
# ============================================================================


@pytest.fixture
def environment_reader(mock_hass: Mock) -> HAEnvironmentReader:
    """Create HAEnvironmentReader with mock HA."""
    return HAEnvironmentReader(
        hass=mock_hass,
        vtherm_entity_id="climate.test_vtherm",
        outdoor_temp_entity_id="sensor.outdoor_temp",
        humidity_in_entity_id="sensor.indoor_humidity",
        humidity_out_entity_id="sensor.outdoor_humidity",
        cloud_cover_entity_id="sensor.cloud_cover",
    )


@pytest.fixture
def scheduler_reader(mock_hass: Mock) -> HASchedulerReader:
    """Create HASchedulerReader with mock HA."""
    return HASchedulerReader(
        hass=mock_hass,
        scheduler_entity_ids=["schedule.heating"],
        vtherm_entity_id="climate.test_vtherm",
    )


@pytest.fixture
def scheduler_commander(mock_hass: Mock) -> HASchedulerCommander:
    """Create HASchedulerCommander with mock HA."""
    return HASchedulerCommander(
        hass=mock_hass,
    )


@pytest.fixture
def climate_data_reader(mock_hass: Mock) -> HAClimateDataReader:
    """Create HAClimateDataReader with mock HA."""
    return HAClimateDataReader(
        hass=mock_hass,
        vtherm_entity_id="climate.test_vtherm",
    )


# ============================================================================
# Use Case Fixtures
# ============================================================================


@pytest.fixture
def control_preheating_use_case(
    scheduler_commander: HASchedulerCommander,
) -> ControlPreheatingUseCase:
    """Create ControlPreheatingUseCase with real adapters."""
    return ControlPreheatingUseCase(scheduler_commander)


@pytest.fixture
def schedule_anticipation_action_use_case(
    scheduler_reader: HASchedulerReader,
    scheduler_commander: HASchedulerCommander,
) -> ScheduleAnticipationActionUseCase:
    """Create ScheduleAnticipationActionUseCase with real adapters."""

    class FakeTimerScheduler:
        """Simple timer scheduler for testing."""

        def __init__(self):
            self.scheduled_timers: list[tuple[datetime, object]] = []

        def schedule_timer(self, target_time: datetime, callback: object) -> object:
            """Schedule a timer and return cancel function."""
            self.scheduled_timers.append((target_time, callback))

            def cancel() -> None:
                pass

            return cancel

    timer_scheduler = FakeTimerScheduler()
    control_preheating = ControlPreheatingUseCase(scheduler_commander)

    return ScheduleAnticipationActionUseCase(
        scheduler_reader=scheduler_reader,
        scheduler_commander=scheduler_commander,
        timer_scheduler=timer_scheduler,
        control_preheating_use_case=control_preheating,
    )


@pytest.fixture
def check_overshoot_risk_use_case(
    scheduler_reader: HASchedulerReader,
    environment_reader: HAEnvironmentReader,
    climate_data_reader: HAClimateDataReader,
    control_preheating_use_case: ControlPreheatingUseCase,
) -> CheckOvershootRiskUseCase:
    """Create CheckOvershootRiskUseCase with real adapters."""
    return CheckOvershootRiskUseCase(
        scheduler_reader=scheduler_reader,
        environment_reader=environment_reader,
        climate_data_reader=climate_data_reader,
        control_preheating=control_preheating_use_case,
        overshoot_threshold_celsius=0.5,
    )


# ============================================================================
# Test Data Helpers
# ============================================================================


@pytest.fixture
def test_now() -> datetime:
    """Current test time."""
    return datetime(2025, 2, 10, 5, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_environment(test_now: datetime) -> EnvironmentState:
    """Sample environment state for testing."""
    return EnvironmentState(
        indoor_temperature=19.0,
        outdoor_temp=5.0,
        humidity=50.0,
        timestamp=test_now,
    )


@pytest.fixture
def sample_timeslot(test_now: datetime) -> ScheduledTimeslot:
    """Sample scheduled timeslot for testing."""
    target_time = test_now.replace(hour=6, minute=30)
    return ScheduledTimeslot(
        target_time=target_time,
        target_temp=21.0,
        timeslot_id="timeslot_1",
        scheduler_entity="schedule.heating",
    )
