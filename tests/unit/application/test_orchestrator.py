"""Tests for HeatingOrchestrator.

Tests verify that the orchestrator correctly composes use cases
and delegates to them without changing behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, PropertyMock

import pytest

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


class TestHeatingOrchestrator:
    """Test suite for HeatingOrchestrator with use case composition."""

    @pytest.fixture
    def mock_calculate_anticipation(self) -> Mock:
        """Create mock CalculateAnticipationUseCase."""
        uc = Mock(spec=CalculateAnticipationUseCase)
        uc.calculate_anticipation_datas = AsyncMock(return_value={
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "anticipation_minutes": None,
            "current_temp": None,
            "learned_heating_slope": None,
            "confidence_level": None,
            "timeslot_id": None,
            "scheduler_entity": None,
        })
        return uc

    @pytest.fixture
    def mock_control_preheating(self) -> Mock:
        """Create mock ControlPreheatingUseCase."""
        uc = Mock(spec=ControlPreheatingUseCase)
        uc.start_preheating = AsyncMock()
        uc.cancel_preheating = AsyncMock()
        uc.is_preheating_active = Mock(return_value=False)
        return uc

    @pytest.fixture
    def mock_schedule_preheating(self) -> Mock:
        """Create mock SchedulePreheatingUseCase."""
        uc = Mock(spec=SchedulePreheatingUseCase)
        uc.create_preheating_scheduler = AsyncMock()
        uc.cancel_preheating_scheduler = AsyncMock()
        return uc

    @pytest.fixture
    def mock_update_cache(self) -> Mock:
        """Create mock UpdateCacheDataUseCase."""
        uc = Mock(spec=UpdateCacheDataUseCase)
        return uc

    @pytest.fixture
    def mock_reset_learning(self) -> Mock:
        """Create mock ResetLearningUseCase."""
        uc = Mock(spec=ResetLearningUseCase)
        uc.reset_all_learning_data = AsyncMock()
        return uc

    @pytest.fixture
    def orchestrator(
        self,
        mock_calculate_anticipation: Mock,
        mock_control_preheating: Mock,
        mock_schedule_preheating: Mock,
        mock_update_cache: Mock,
        mock_reset_learning: Mock,
    ) -> HeatingOrchestrator:
        """Create HeatingOrchestrator instance with mocked use cases."""
        return HeatingOrchestrator(
            calculate_anticipation=mock_calculate_anticipation,
            control_preheating=mock_control_preheating,
            schedule_preheating=mock_schedule_preheating,
            update_cache=mock_update_cache,
            reset_learning=mock_reset_learning,
        )

    @pytest.mark.asyncio
    async def test_calculate_anticipation_only_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
    ) -> None:
        """Test that calculate_anticipation_only delegates to use case."""
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc)

        await orchestrator.calculate_anticipation_only(
            target_time=target_time,
            target_temp=21.0,
        )

        mock_calculate_anticipation.calculate_anticipation_datas.assert_called_once_with(
            target_time=target_time,
            target_temp=21.0,
        )

    @pytest.mark.asyncio
    async def test_calculate_anticipation_only_returns_result(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
    ) -> None:
        """Test that calculate_anticipation_only returns use case result."""
        expected_data = {
            "anticipated_start_time": datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc),
            "next_schedule_time": datetime(2025, 2, 10, 11, 0, 0, tzinfo=timezone.utc),
            "anticipation_minutes": 60,
        }
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = expected_data

        result = await orchestrator.calculate_anticipation_only()

        assert result == expected_data

    @pytest.mark.asyncio
    async def test_enable_preheating_calculates_and_schedules(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_preheating: Mock,
    ) -> None:
        """Test that enable_preheating calculates anticipation and schedules timer."""
        anticipated = datetime(2025, 2, 10, 9, 30, 0, tzinfo=timezone.utc)
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = {
            "anticipated_start_time": anticipated,
            "next_schedule_time": datetime(2025, 2, 10, 10, 0, 0, tzinfo=timezone.utc),
            "next_target_temperature": 21.0,
            "scheduler_entity": "schedule.heating",
        }

        result = await orchestrator.enable_preheating()

        mock_calculate_anticipation.calculate_anticipation_datas.assert_called_once()
        mock_schedule_preheating.create_preheating_scheduler.assert_called_once()
        assert result["anticipated_start_time"] == anticipated

    @pytest.mark.asyncio
    async def test_enable_preheating_skips_scheduling_when_no_data(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_preheating: Mock,
    ) -> None:
        """Test that enable_preheating skips scheduling when no valid data."""
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = {
            "anticipated_start_time": None,
        }

        await orchestrator.enable_preheating()

        mock_schedule_preheating.create_preheating_scheduler.assert_not_called()

    @pytest.mark.asyncio
    async def test_disable_preheating_cancels_timer_and_preheating(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_preheating: Mock,
    ) -> None:
        """Test that disable_preheating cancels timer and active preheating."""
        mock_control_preheating.is_preheating_active.return_value = True

        await orchestrator.disable_preheating(scheduler_entity_id="schedule.heating")

        mock_schedule_preheating.cancel_preheating_scheduler.assert_called_once()
        mock_control_preheating.cancel_preheating.assert_called_once_with("schedule.heating")

    @pytest.mark.asyncio
    async def test_disable_preheating_skips_cancel_when_not_active(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_preheating: Mock,
    ) -> None:
        """Test that disable_preheating doesn't cancel preheating if not active."""
        mock_control_preheating.is_preheating_active.return_value = False

        await orchestrator.disable_preheating(scheduler_entity_id="schedule.heating")

        mock_schedule_preheating.cancel_preheating_scheduler.assert_called_once()
        mock_control_preheating.cancel_preheating.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_preheating_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_preheating: Mock,
    ) -> None:
        """Test that cancel_preheating cancels timer and preheating action."""
        await orchestrator.cancel_preheating(scheduler_entity_id="schedule.heating")

        mock_schedule_preheating.cancel_preheating_scheduler.assert_called_once()
        mock_control_preheating.cancel_preheating.assert_called_once_with("schedule.heating")

    @pytest.mark.asyncio
    async def test_reset_all_learning_data_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_reset_learning: Mock,
    ) -> None:
        """Test that reset_all_learning_data delegates to use case."""
        await orchestrator.reset_all_learning_data(device_id="test_device")

        mock_reset_learning.reset_all_learning_data.assert_called_once_with("test_device")

    def test_is_preheating_active_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
    ) -> None:
        """Test that is_preheating_active delegates to use case."""
        mock_control_preheating.is_preheating_active.return_value = False
        assert orchestrator.is_preheating_active() is False

        mock_control_preheating.is_preheating_active.return_value = True
        assert orchestrator.is_preheating_active() is True
