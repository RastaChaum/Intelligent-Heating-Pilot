"""Unit tests for decision strategies."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ISchedulerReader,
    IModelStorage,
)
from custom_components.intelligent_heating_pilot.domain.services.simple_decision_strategy import (
    SimpleDecisionStrategy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HeatingAction,
    ScheduledTimeslot,
)


@pytest.fixture
def mock_scheduler_reader():
    """Create a mock scheduler reader."""
    return AsyncMock(spec=ISchedulerReader)


@pytest.fixture
def mock_model_storage():
    """Create a mock model storage."""
    storage = AsyncMock(spec=IModelStorage)
    storage.get_learned_heating_slope.return_value = 2.0  # 2°C/hour
    return storage


@pytest.fixture
def simple_strategy(mock_scheduler_reader, mock_model_storage):
    """Create a simple decision strategy with mocked dependencies."""
    return SimpleDecisionStrategy(
        scheduler_reader=mock_scheduler_reader,
        model_storage=mock_model_storage,
    )


class TestSimpleDecisionStrategy:
    """Test suite for SimpleDecisionStrategy."""
    
    async def test_no_action_when_no_timeslots(
        self, 
        simple_strategy, 
        mock_scheduler_reader
    ):
        """Should return NO_ACTION when no scheduled timeslots exist."""
        # GIVEN: No scheduled timeslots
        mock_scheduler_reader.get_next_timeslot.return_value = None
        
        environment = EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=datetime.now(),
        )
        
        # WHEN: Deciding action
        decision = await simple_strategy.decide_heating_action(environment)
        
        # THEN: Should not take action
        assert decision.action == HeatingAction.NO_ACTION
        assert "No scheduled timeslots" in decision.reason
    
    async def test_no_action_when_already_at_target(
        self,
        simple_strategy,
        mock_scheduler_reader,
    ):
        """Should return NO_ACTION when already at target temperature."""
        # GIVEN: Already at target temperature
        target_time = datetime.now() + timedelta(hours=1)
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=20.0,
            timeslot_id="test_slot",
        )
        
        environment = EnvironmentState(
            indoor_temperature=20.5,  # Already above target
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=datetime.now(),
        )
        
        # WHEN: Deciding action
        decision = await simple_strategy.decide_heating_action(environment)
        
        # THEN: Should not heat
        assert decision.action == HeatingAction.NO_ACTION
        assert "Already at target" in decision.reason
    
    async def test_start_heating_when_time_reached(
        self,
        simple_strategy,
        mock_scheduler_reader,
        mock_model_storage,
    ):
        """Should START_HEATING when anticipated start time is reached."""
        # GIVEN: Current temp below target, start time reached
        now = datetime.now()
        target_time = now + timedelta(hours=2)
        
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=20.0,
            timeslot_id="test_slot",
        )
        
        mock_model_storage.get_learned_heating_slope.return_value = 2.0  # 2°C/hour
        
        environment = EnvironmentState(
            indoor_temperature=16.0,  # 4°C below target
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=now,
        )
        
        # WHEN: Deciding action
        decision = await simple_strategy.decide_heating_action(environment)
        
        # THEN: Should start heating
        # With 4°C to gain at 2°C/hour = 2 hours needed
        # Target in 2 hours = should start now
        assert decision.action == HeatingAction.START_HEATING
        assert decision.target_temp == 20.0
    
    async def test_wait_when_too_early(
        self,
        simple_strategy,
        mock_scheduler_reader,
        mock_model_storage,
    ):
        """Should wait when it's too early to start heating."""
        # GIVEN: Current temp below target, but plenty of time
        now = datetime.now()
        target_time = now + timedelta(hours=5)  # 5 hours away
        
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=20.0,
            timeslot_id="test_slot",
        )
        
        mock_model_storage.get_learned_heating_slope.return_value = 2.0  # 2°C/hour
        
        environment = EnvironmentState(
            indoor_temperature=16.0,  # 4°C below target
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=now,
        )
        
        # WHEN: Deciding action
        decision = await simple_strategy.decide_heating_action(environment)
        
        # THEN: Should wait
        # With 4°C to gain at 2°C/hour = 2 hours needed
        # Target in 5 hours = wait 3 more hours
        assert decision.action == HeatingAction.NO_ACTION
        assert "Wait until" in decision.reason
    
    async def test_stop_heating_on_overshoot_risk(
        self,
        simple_strategy,
        mock_scheduler_reader,
    ):
        """Should STOP_HEATING when overshoot risk is detected."""
        # GIVEN: High heating slope with risk of overshooting
        now = datetime.now()
        target_time = now + timedelta(hours=1)
        
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=20.0,
            timeslot_id="test_slot",
        )
        
        environment = EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=now,
        )
        
        # WHEN: Checking overshoot with high slope
        # At 3°C/hour, in 1 hour: 18 + 3 = 21°C (> 20.5 threshold)
        decision = await simple_strategy.check_overshoot_risk(
            environment=environment,
            current_slope=3.0,  # High slope
        )
        
        # THEN: Should stop heating
        assert decision.action == HeatingAction.STOP_HEATING
        assert "Overshoot risk" in decision.reason
    
    async def test_no_stop_when_no_overshoot_risk(
        self,
        simple_strategy,
        mock_scheduler_reader,
    ):
        """Should continue heating when no overshoot risk."""
        # GIVEN: Moderate heating slope, no overshoot risk
        now = datetime.now()
        target_time = now + timedelta(hours=1)
        
        mock_scheduler_reader.get_next_timeslot.return_value = ScheduledTimeslot(
            target_time=target_time,
            target_temp=20.0,
            timeslot_id="test_slot",
        )
        
        environment = EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=now,
        )
        
        # WHEN: Checking overshoot with moderate slope
        # At 1.5°C/hour, in 1 hour: 18 + 1.5 = 19.5°C (< 20.5 threshold)
        decision = await simple_strategy.check_overshoot_risk(
            environment=environment,
            current_slope=1.5,  # Moderate slope
        )
        
        # THEN: Should continue
        assert decision.action == HeatingAction.NO_ACTION
        assert "No overshoot risk" in decision.reason
