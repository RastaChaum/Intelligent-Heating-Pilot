"""Tests for ResetLearningUseCase.

STEP 1: Tests verify that the use case correctly delegates to
HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    ResetLearningUseCase,
)


class TestResetLearningUseCase:
    """Test suite for ResetLearningUseCase.

    STEP 1: Verify delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service.reset_learned_slopes = AsyncMock()
        return service

    @pytest.fixture
    def use_case(self, mock_app_service: Mock) -> ResetLearningUseCase:
        """Create ResetLearningUseCase instance."""
        return ResetLearningUseCase(mock_app_service)

    @pytest.mark.asyncio
    async def test_execute_delegates_to_app_service(
        self,
        use_case: ResetLearningUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() delegates to application service.

        STEP 1: Verify delegation pattern.
        """
        # GIVEN: Use case is initialized with mock service
        # WHEN: Execute is called
        await use_case.execute()

        # THEN: Application service reset method is called once
        mock_app_service.reset_learned_slopes.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_no_return_value(
        self,
        use_case: ResetLearningUseCase,
        mock_app_service: Mock,
    ) -> None:
        """Test that execute() has no return value.

        STEP 1: Verify void return.
        """
        # WHEN: Execute is called
        result = await use_case.execute()

        # THEN: Result is None
        assert result is None
