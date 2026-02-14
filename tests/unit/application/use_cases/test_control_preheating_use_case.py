"""Tests for ControlPreheatingUseCase.

STEP 1: Tests verify that the use case correctly delegates to
HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
)


class TestControlPreheatingUseCase:
    """Test suite for ControlPreheatingUseCase.

    STEP 1: Verify delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service._clear_anticipation_state = AsyncMock()
        service._trigger_anticipation_action = AsyncMock()
        service._is_preheating_active = False
        service._preheating_target_time = None
        return service

    @pytest.fixture
    def use_case(self, mock_app_service: Mock) -> ControlPreheatingUseCase:
        """Create ControlPreheatingUseCase instance."""
        return ControlPreheatingUseCase(mock_app_service)

    @pytest.mark.asyncio
    async def test_clear_anticipation_state_delegates(
        self,
        use_case: ControlPreheatingUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that clear_anticipation_state() delegates to application service.

        STEP 1: Verify delegation pattern.
        """
        # WHEN: clear_anticipation_state is called
        await use_case.clear_anticipation_state()

        # THEN: Application service method is called
        mock_app_service._clear_anticipation_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_anticipation_action_delegates(
        self,
        use_case: ControlPreheatingUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that trigger_anticipation_action() delegates to application service.

        STEP 1: Verify delegation with parameters.
        """
        # GIVEN: Parameters for triggering action
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        target_temp = 21.0
        scheduler_entity_id = "schedule.heating"

        # WHEN: trigger_anticipation_action is called
        await use_case.trigger_anticipation_action(
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
        )

        # THEN: Application service method is called with same parameters
        mock_app_service._trigger_anticipation_action.assert_called_once_with(
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
        )

    def test_is_preheating_active_returns_state(
        self,
        use_case: ControlPreheatingUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that is_preheating_active() returns application service state.

        STEP 1: Verify state read.
        """
        # GIVEN: Application service has preheating inactive
        mock_app_service._is_preheating_active = False

        # WHEN: is_preheating_active is called
        result = use_case.is_preheating_active()

        # THEN: Result matches service state
        assert result is False

        # GIVEN: Application service has preheating active
        mock_app_service._is_preheating_active = True

        # WHEN: is_preheating_active is called again
        result = use_case.is_preheating_active()

        # THEN: Result matches updated service state
        assert result is True

    def test_get_preheating_target_time_returns_state(
        self,
        use_case: ControlPreheatingUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that get_preheating_target_time() returns application service state.

        STEP 1: Verify state read.
        """
        # GIVEN: Application service has no target time
        mock_app_service._preheating_target_time = None

        # WHEN: get_preheating_target_time is called
        result = use_case.get_preheating_target_time()

        # THEN: Result is None
        assert result is None

        # GIVEN: Application service has a target time
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        mock_app_service._preheating_target_time = target_time

        # WHEN: get_preheating_target_time is called again
        result = use_case.get_preheating_target_time()

        # THEN: Result matches service state
        assert result == target_time
