"""Tests for HeatingOrchestrator.

Tests verify that the orchestrator correctly composes use cases
and delegates to them without changing behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, call

import pytest

from custom_components.intelligent_heating_pilot.application.orchestrator import (
    HeatingOrchestrator,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    CalculateAnticipationUseCase,
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
    UpdateCacheDataUseCase,
)


class TestHeatingOrchestrator:
    """Test suite for HeatingOrchestrator with use case composition."""

    @pytest.fixture
    def mock_calculate_anticipation(self) -> Mock:
        """Create mock CalculateAnticipationUseCase."""
        uc = Mock(spec=CalculateAnticipationUseCase)
        uc.calculate_anticipation_datas = AsyncMock(
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
    def mock_schedule_anticipation_action(self) -> Mock:
        """Create mock ScheduleAnticipationActionUseCase."""
        uc = Mock(spec=ScheduleAnticipationActionUseCase)
        uc.schedule_action = AsyncMock()
        uc.cancel_action = AsyncMock()
        return uc

    @pytest.fixture
    def mock_update_cache(self) -> Mock:
        """Create mock UpdateCacheDataUseCase."""
        uc = Mock(spec=UpdateCacheDataUseCase)
        uc.reset_cache = AsyncMock()
        return uc

    @pytest.fixture
    def orchestrator(
        self,
        mock_calculate_anticipation: Mock,
        mock_control_preheating: Mock,
        mock_schedule_anticipation_action: Mock,
        mock_update_cache: Mock,
    ) -> HeatingOrchestrator:
        """Create HeatingOrchestrator instance with mocked use cases."""
        return HeatingOrchestrator(
            calculate_anticipation=mock_calculate_anticipation,
            control_preheating=mock_control_preheating,
            schedule_anticipation_action=mock_schedule_anticipation_action,
            update_cache=mock_update_cache,
        )

    @pytest.mark.asyncio
    async def test_calculate_anticipation_only_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
    ) -> None:
        """Test that calculate_anticipation_only delegates to use case."""
        target_time = datetime(2025, 2, 10, 10, 0, 0, tzinfo=UTC)

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
            "anticipated_start_time": datetime(2025, 2, 10, 10, 0, 0, tzinfo=UTC),
            "next_schedule_time": datetime(2025, 2, 10, 11, 0, 0, tzinfo=UTC),
            "anticipation_minutes": 60,
        }
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = expected_data

        result = await orchestrator.calculate_anticipation_only()

        assert result == expected_data

    @pytest.mark.asyncio
    async def test_disable_preheating_cancels_timer_and_preheating(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """Test that disable_preheating cancels timer and active preheating."""
        mock_control_preheating.is_preheating_active.return_value = True

        await orchestrator.disable_preheating(scheduler_entity_id="schedule.heating")

        mock_schedule_anticipation_action.cancel_action.assert_called_once()
        mock_control_preheating.cancel_preheating.assert_called_once_with("schedule.heating")

    @pytest.mark.asyncio
    async def test_cancel_pending_anticipation_cancels_timer_only(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """Pending timer is cancelled without reverting the thermostat (used on unload)."""
        mock_control_preheating.is_preheating_active.return_value = True

        await orchestrator.cancel_pending_anticipation()

        mock_schedule_anticipation_action.cancel_action.assert_awaited_once()
        mock_control_preheating.cancel_preheating.assert_not_called()

    @pytest.mark.asyncio
    async def test_disable_preheating_skips_cancel_when_not_active(
        self,
        orchestrator: HeatingOrchestrator,
        mock_control_preheating: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """Test that disable_preheating calls cancel_preheating regardless of state.

        With callee-side validation, the orchestrator always calls cancel_preheating,
        and cancel_preheating handles the internal check for active state.
        """
        mock_control_preheating.is_preheating_active.return_value = False

        await orchestrator.disable_preheating(scheduler_entity_id="schedule.heating")

        mock_schedule_anticipation_action.cancel_action.assert_called_once()
        # With callee-side validation, cancel_preheating is always called
        mock_control_preheating.cancel_preheating.assert_called_once_with("schedule.heating")

    @pytest.mark.asyncio
    async def test_reset_all_learning_data_delegates(
        self,
        orchestrator: HeatingOrchestrator,
        mock_update_cache: Mock,
    ) -> None:
        """Test that reset_all_learning_data delegates to update_cache.reset_cache()."""
        await orchestrator.reset_all_learning_data(device_id="test_device")

        mock_update_cache.reset_cache.assert_called_once_with("test_device")

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


class TestHeatingOrchestratorSchedulerFallback:
    """Tests for the retry-on-blocked-scheduler loop added for issue #64."""

    @pytest.fixture
    def mock_calculate_anticipation(self) -> Mock:
        uc = Mock(spec=CalculateAnticipationUseCase)
        uc.calculate_anticipation_datas = AsyncMock()
        return uc

    @pytest.fixture
    def mock_schedule_anticipation_action(self) -> Mock:
        uc = Mock(spec=ScheduleAnticipationActionUseCase)
        uc.handle_anticipation_scheduling = AsyncMock()
        return uc

    @pytest.fixture
    def orchestrator(
        self,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> HeatingOrchestrator:
        control_preheating = Mock(spec=ControlPreheatingUseCase)
        update_cache = Mock(spec=UpdateCacheDataUseCase)
        return HeatingOrchestrator(
            calculate_anticipation=mock_calculate_anticipation,
            control_preheating=control_preheating,
            schedule_anticipation_action=mock_schedule_anticipation_action,
            update_cache=update_cache,
        )

    def _data(self, scheduler_entity: str | None, anticipated_start) -> dict:
        return {
            "anticipated_start_time": anticipated_start,
            "scheduler_entity": scheduler_entity,
        }

    @pytest.mark.asyncio
    async def test_no_fallback_needed_on_first_success(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """A confirmed-successful first attempt does not retry and reports not blocked."""
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = self._data(
            "switch.non_vacation", datetime(2025, 2, 10, 4, 30, tzinfo=UTC)
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling.return_value = None

        result = await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        mock_calculate_anticipation.calculate_anticipation_datas.assert_called_once_with(
            exclude_entity_ids=frozenset()
        )
        assert result["scheduler_blocked"] is False
        assert result["blocked_schedulers"] == []

    @pytest.mark.asyncio
    async def test_retries_excluding_blocked_scheduler_until_success(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """A blocked first candidate triggers a retry excluding it (the #64 scenario)."""
        first_attempt = self._data("switch.non_vacation", datetime(2025, 2, 10, 4, 30, tzinfo=UTC))
        second_attempt = self._data("switch.vacation", datetime(2025, 2, 10, 6, 0, tzinfo=UTC))
        mock_calculate_anticipation.calculate_anticipation_datas = AsyncMock(
            side_effect=[first_attempt, second_attempt]
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling = AsyncMock(
            side_effect=["switch.non_vacation", None]
        )

        result = await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        assert mock_calculate_anticipation.calculate_anticipation_datas.call_args_list == [
            call(exclude_entity_ids=frozenset()),
            call(exclude_entity_ids=frozenset({"switch.non_vacation"})),
        ]
        assert result is second_attempt
        assert result["scheduler_blocked"] is False
        assert result["blocked_schedulers"] == ["switch.non_vacation"]

    @pytest.mark.asyncio
    async def test_exhausting_all_candidates_reports_blocked(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """When every candidate is confirmed blocked, the cycle stops and reports it."""
        first_attempt = self._data("switch.a", datetime(2025, 2, 10, 4, 30, tzinfo=UTC))
        second_attempt = self._data("switch.b", datetime(2025, 2, 10, 5, 0, tzinfo=UTC))
        exhausted = self._data(None, None)  # no candidate left -> no anticipated_start_time
        mock_calculate_anticipation.calculate_anticipation_datas = AsyncMock(
            side_effect=[first_attempt, second_attempt, exhausted]
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling = AsyncMock(
            side_effect=["switch.a", "switch.b", None]
        )

        result = await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        assert result["scheduler_blocked"] is True
        assert result["blocked_schedulers"] == ["switch.a", "switch.b"]

    @pytest.mark.asyncio
    async def test_excluded_set_not_carried_over_between_separate_calls(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """FR-004a: exclusion is scoped to one cycle; the next call starts fresh."""
        mock_calculate_anticipation.calculate_anticipation_datas = AsyncMock(
            side_effect=[
                self._data("switch.a", datetime(2025, 2, 10, 4, 30, tzinfo=UTC)),
                self._data(None, None),
            ]
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling = AsyncMock(
            side_effect=["switch.a", None]
        )
        await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        # Second, independent call: reset mocks to observe only this call's exclude set
        mock_calculate_anticipation.calculate_anticipation_datas = AsyncMock(
            return_value=self._data("switch.a", datetime(2025, 2, 10, 4, 30, tzinfo=UTC))
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling = AsyncMock(
            return_value=None
        )

        await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

        mock_calculate_anticipation.calculate_anticipation_datas.assert_called_once_with(
            exclude_entity_ids=frozenset()
        )

    @pytest.mark.asyncio
    async def test_retry_after_blocked_scheduler_seeds_exclusion(
        self,
        orchestrator: HeatingOrchestrator,
        mock_calculate_anticipation: Mock,
        mock_schedule_anticipation_action: Mock,
    ) -> None:
        """The timer-fired re-entry point seeds the exclusion set with the blocked id."""
        mock_calculate_anticipation.calculate_anticipation_datas.return_value = self._data(
            "switch.vacation", datetime(2025, 2, 10, 6, 0, tzinfo=UTC)
        )
        mock_schedule_anticipation_action.handle_anticipation_scheduling.return_value = None

        await orchestrator.retry_anticipation_after_blocked_scheduler("switch.non_vacation")

        mock_calculate_anticipation.calculate_anticipation_datas.assert_called_once_with(
            exclude_entity_ids=frozenset({"switch.non_vacation"})
        )
