"""Tests for CalculateAnticipationUseCase.

STEP 1: Tests verify that the use case correctly delegates to
HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    CalculateAnticipationUseCase,
)


class TestCalculateAnticipationUseCase:
    """Test suite for CalculateAnticipationUseCase.

    STEP 1: Verify delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
        return service

    @pytest.fixture
    def use_case(self, mock_app_service: Mock) -> CalculateAnticipationUseCase:
        """Create CalculateAnticipationUseCase instance."""
        return CalculateAnticipationUseCase(mock_app_service)

    @pytest.mark.asyncio
    async def test_execute_delegates_to_app_service(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() delegates to application service.

        STEP 1: Verify delegation pattern.
        """
        # GIVEN: Use case is initialized with mock service
        # WHEN: Execute is called with ihp_enabled=True
        await use_case.execute(ihp_enabled=True)

        # THEN: Application service method is called with same parameters
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once_with(
            ihp_enabled=True
        )

    @pytest.mark.asyncio
    async def test_execute_with_ihp_disabled(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test execution with IHP disabled.

        STEP 1: Verify delegation with ihp_enabled=False.
        """
        # WHEN: Execute is called with ihp_enabled=False
        await use_case.execute(ihp_enabled=False)

        # THEN: Application service receives ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once_with(
            ihp_enabled=False
        )

    @pytest.mark.asyncio
    async def test_execute_returns_result(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() returns application service result.

        STEP 1: Verify return value passthrough.
        """
        # GIVEN: Application service returns anticipation data
        expected_data = {
            "anticipated_start_time": "2025-02-10T10:00:00",
            "next_schedule_time": "2025-02-10T11:00:00",
            "anticipation_minutes": 60,
        }
        mock_app_service.calculate_and_schedule_anticipation.return_value = expected_data

        # WHEN: Execute is called
        result = await use_case.execute(ihp_enabled=True)

        # THEN: Result matches application service return value
        assert result == expected_data

    @pytest.mark.asyncio
    async def test_execute_returns_none_when_no_schedule(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() returns None when no schedule available.

        STEP 1: Verify None passthrough.
        """
        # GIVEN: Application service returns None (no schedule)
        mock_app_service.calculate_and_schedule_anticipation.return_value = None

        # WHEN: Execute is called
        result = await use_case.execute(ihp_enabled=True)

        # THEN: Result is None
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_returns_clear_values_dict(
        self,
        use_case: CalculateAnticipationUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() returns clear_values dict when appropriate.

        STEP 1: Verify clear_values dict passthrough.
        """
        # GIVEN: Application service returns clear_values signal
        mock_app_service.calculate_and_schedule_anticipation.return_value = {
            "clear_values": True
        }

        # WHEN: Execute is called
        result = await use_case.execute(ihp_enabled=True)

        # THEN: Result contains clear_values flag
        assert result == {"clear_values": True}
