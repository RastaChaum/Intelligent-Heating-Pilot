"""Tests for ScheduleAnticipationActionUseCase.

STEP 1: Tests verify that the use case correctly delegates to
HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ScheduleAnticipationActionUseCase,
)


class TestScheduleAnticipationActionUseCase:
    """Test suite for ScheduleAnticipationActionUseCase.

    STEP 1: Verify delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service._schedule_anticipation = AsyncMock()
        service._cancel_anticipation_timer = AsyncMock()
        return service

    @pytest.fixture
    def use_case(
        self, mock_app_service: Mock
    ) -> ScheduleAnticipationActionUseCase:
        """Create ScheduleAnticipationActionUseCase instance."""
        return ScheduleAnticipationActionUseCase(mock_app_service)

    @pytest.mark.asyncio
    async def test_execute_delegates_to_app_service(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() delegates to application service.

        STEP 1: Verify delegation pattern with parameters.
        """
        # GIVEN: Parameters for scheduling
        anticipated_start = datetime(2025, 2, 10, 10, 0, 0)
        target_time = datetime(2025, 2, 10, 11, 0, 0)
        target_temp = 21.0
        scheduler_entity_id = "schedule.heating"
        lhs = 1.5

        # WHEN: Execute is called
        await use_case.execute(
            anticipated_start=anticipated_start,
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
            lhs=lhs,
        )

        # THEN: Application service method is called with same parameters
        mock_app_service._schedule_anticipation.assert_called_once_with(
            anticipated_start=anticipated_start,
            target_time=target_time,
            target_temp=target_temp,
            scheduler_entity_id=scheduler_entity_id,
            lhs=lhs,
        )

    @pytest.mark.asyncio
    async def test_cancel_anticipation_timer_delegates(
        self,
        use_case: ScheduleAnticipationActionUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that cancel_anticipation_timer() delegates to application service.

        STEP 1: Verify delegation pattern.
        """
        # WHEN: cancel_anticipation_timer is called
        await use_case.cancel_anticipation_timer()

        # THEN: Application service method is called
        mock_app_service._cancel_anticipation_timer.assert_called_once()
