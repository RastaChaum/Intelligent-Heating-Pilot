"""Unit tests for HeatingPilot with strategy pattern."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.entities.heating_pilot import (
    HeatingPilot,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ISchedulerCommander,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.decision_strategy import (
    IDecisionStrategy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HeatingAction,
    HeatingDecision,
)


@pytest.fixture
def mock_decision_strategy():
    """Create a mock decision strategy."""
    return AsyncMock(spec=IDecisionStrategy)


@pytest.fixture
def mock_scheduler_commander():
    """Create a mock scheduler commander."""
    return AsyncMock(spec=ISchedulerCommander)


@pytest.fixture
def heating_pilot(mock_decision_strategy, mock_scheduler_commander):
    """Create a heating pilot with mocked dependencies."""
    return HeatingPilot(
        decision_strategy=mock_decision_strategy,
        scheduler_commander=mock_scheduler_commander,
    )


class TestHeatingPilotWithStrategy:
    """Test suite for HeatingPilot using strategy pattern."""
    
    async def test_delegates_decision_to_strategy(
        self,
        heating_pilot,
        mock_decision_strategy,
    ):
        """Should delegate heating decision to configured strategy."""
        # GIVEN: Strategy returns START_HEATING
        mock_decision_strategy.decide_heating_action.return_value = HeatingDecision(
            action=HeatingAction.START_HEATING,
            target_temp=20.0,
            reason="Strategy decided to start heating",
        )
        
        environment = EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=datetime.now(),
        )
        
        # WHEN: Deciding action
        decision = await heating_pilot.decide_heating_action(environment)
        
        # THEN: Should use strategy's decision
        assert decision.action == HeatingAction.START_HEATING
        assert decision.target_temp == 20.0
        mock_decision_strategy.decide_heating_action.assert_called_once_with(environment)
    
    async def test_delegates_overshoot_check_to_strategy(
        self,
        heating_pilot,
        mock_decision_strategy,
    ):
        """Should delegate overshoot check to configured strategy."""
        # GIVEN: Strategy returns STOP_HEATING
        mock_decision_strategy.check_overshoot_risk.return_value = HeatingDecision(
            action=HeatingAction.STOP_HEATING,
            reason="Strategy detected overshoot risk",
        )
        
        environment = EnvironmentState(
            indoor_temperature=19.5,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=datetime.now(),
        )
        
        # WHEN: Checking overshoot
        decision = await heating_pilot.check_overshoot_risk(
            environment=environment,
            current_slope=2.5,
        )
        
        # THEN: Should use strategy's decision
        assert decision.action == HeatingAction.STOP_HEATING
        mock_decision_strategy.check_overshoot_risk.assert_called_once_with(
            environment,
            2.5,
        )
    
    async def test_can_use_different_strategies(self, mock_scheduler_commander):
        """Should work with any strategy implementation."""
        # GIVEN: Two different strategy implementations
        simple_strategy = AsyncMock(spec=IDecisionStrategy)
        simple_strategy.decide_heating_action.return_value = HeatingDecision(
            action=HeatingAction.NO_ACTION,
            reason="Simple strategy says wait",
        )
        
        ml_strategy = AsyncMock(spec=IDecisionStrategy)
        ml_strategy.decide_heating_action.return_value = HeatingDecision(
            action=HeatingAction.START_HEATING,
            target_temp=21.0,
            reason="ML strategy predicts start now",
        )
        
        environment = EnvironmentState(
            indoor_temperature=18.0,
            outdoor_temp=5.0,
            indoor_humidity=50.0,
            cloud_coverage=0.5,
            timestamp=datetime.now(),
        )
        
        # WHEN: Using simple strategy
        pilot_simple = HeatingPilot(
            decision_strategy=simple_strategy,
            scheduler_commander=mock_scheduler_commander,
        )
        decision_simple = await pilot_simple.decide_heating_action(environment)
        
        # THEN: Gets simple strategy decision
        assert decision_simple.action == HeatingAction.NO_ACTION
        
        # WHEN: Using ML strategy
        pilot_ml = HeatingPilot(
            decision_strategy=ml_strategy,
            scheduler_commander=mock_scheduler_commander,
        )
        decision_ml = await pilot_ml.decide_heating_action(environment)
        
        # THEN: Gets ML strategy decision
        assert decision_ml.action == HeatingAction.START_HEATING
        assert decision_ml.target_temp == 21.0
