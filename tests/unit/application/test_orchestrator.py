"""Tests for HeatingOrchestrator.

STEP 1: Tests verify that the orchestrator correctly composes use cases
and delegates to HeatingApplicationService without changing behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.orchestrator import (
    HeatingOrchestrator,
)


class TestHeatingOrchestrator:
    """Test suite for HeatingOrchestrator.

    STEP 1: Verify composition and delegation to HeatingApplicationService.
    """

    @pytest.fixture
    def mock_app_service(self) -> Mock:
        """Create mock HeatingApplicationService."""
        service = Mock()
        service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
        service.reset_learned_slopes = AsyncMock()
        service._clear_anticipation_state = AsyncMock()
        service._is_preheating_active = False
        return service

    @pytest.fixture
    def orchestrator(self, mock_app_service: Mock) -> HeatingOrchestrator:
        """Create HeatingOrchestrator instance."""
        return HeatingOrchestrator(mock_app_service)

    @pytest.mark.asyncio
    async def test_calculate_and_schedule_anticipation_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that calculate_and_schedule_anticipation delegates to use case.

        STEP 1: Verify delegation through use case.
        """
        # WHEN: Orchestrator method is called with ihp_enabled=True
        await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        # THEN: Application service is called through use case
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once_with(
            ihp_enabled=True
        )

    @pytest.mark.asyncio
    async def test_calculate_and_schedule_anticipation_with_ihp_disabled(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test calculate_and_schedule_anticipation with IHP disabled.

        STEP 1: Verify delegation with ihp_enabled=False.
        """
        # WHEN: Orchestrator method is called with ihp_enabled=False
        await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=False)

        # THEN: Application service receives ihp_enabled=False
        mock_app_service.calculate_and_schedule_anticipation.assert_called_once_with(
            ihp_enabled=False
        )

    @pytest.mark.asyncio
    async def test_calculate_and_schedule_anticipation_returns_result(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that orchestrator returns use case result.

        STEP 1: Verify return value passthrough.
        """
        # GIVEN: Application service returns anticipation data
        expected_data = {
            "anticipated_start_time": "2025-02-10T10:00:00",
            "next_schedule_time": "2025-02-10T11:00:00",
            "anticipation_minutes": 60,
        }
        mock_app_service.calculate_and_schedule_anticipation.return_value = expected_data

        # WHEN: Orchestrator method is called
        result = await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        # THEN: Result matches application service return value
        assert result == expected_data

    @pytest.mark.asyncio
    async def test_reset_learned_slopes_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that reset_learned_slopes delegates to use case.

        STEP 1: Verify delegation through use case.
        """
        # WHEN: Orchestrator method is called
        await orchestrator.reset_learned_slopes()

        # THEN: Application service is called through use case
        mock_app_service.reset_learned_slopes.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_anticipation_state_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that clear_anticipation_state delegates to use case.

        STEP 1: Verify delegation through use case.
        """
        # WHEN: Orchestrator method is called
        await orchestrator.clear_anticipation_state()

        # THEN: Application service is called through use case
        mock_app_service._clear_anticipation_state.assert_called_once()

    def test_is_preheating_active_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that is_preheating_active delegates to use case.

        STEP 1: Verify delegation through use case.
        """
        # GIVEN: Application service has preheating inactive
        mock_app_service._is_preheating_active = False

        # WHEN: Orchestrator method is called
        result = orchestrator.is_preheating_active()

        # THEN: Result matches service state
        assert result is False

        # GIVEN: Application service has preheating active
        mock_app_service._is_preheating_active = True

        # WHEN: Orchestrator method is called again
        result = orchestrator.is_preheating_active()

        # THEN: Result matches updated service state
        assert result is True

    def test_application_service_property(
        self,
        orchestrator: HeatingOrchestrator,
        mock_app_service: Mock,
    ) -> None:
        """Test that application_service property returns the service.

        STEP 1: Verify backward compatibility property.
        This property will be removed in STEP 3.
        """
        # WHEN: application_service property is accessed
        result = orchestrator.application_service

        # THEN: Result is the mock service
        assert result is mock_app_service
