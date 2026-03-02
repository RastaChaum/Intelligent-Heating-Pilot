"""Tests for SchedulePreheatingUseCase.

Tests verify that the use case correctly delegates to
ITimerScheduler for scheduling and canceling preheating timers.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.use_cases import (
    SchedulePreheatingUseCase,
)


class TestSchedulePreheatingUseCase:
    """Test suite for SchedulePreheatingUseCase.

    Verifies delegation to ITimerScheduler.
    """

    @pytest.fixture
    def mock_timer_scheduler(self) -> Mock:
        """Create mock ITimerScheduler."""
        scheduler = Mock()
        cancel_callback = Mock()
        scheduler.schedule_timer = Mock(return_value=cancel_callback)
        return scheduler

    @pytest.fixture
    def use_case(
        self, mock_timer_scheduler: Mock
    ) -> SchedulePreheatingUseCase:
        """Create SchedulePreheatingUseCase instance."""
        return SchedulePreheatingUseCase(mock_timer_scheduler)

    @pytest.mark.asyncio
    async def test_create_preheating_scheduler_delegates(
        self,
        use_case: SchedulePreheatingUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test that create_preheating_scheduler() delegates to timer scheduler.

        Verifies delegation pattern with parameters.
        """
        # GIVEN: Parameters for scheduling
        anticipated_start = datetime(2025, 2, 10, 10, 0, 0)
        preheating_callback = Mock()

        # WHEN: create_preheating_scheduler is called
        await use_case.create_preheating_scheduler(
            anticipated_start=anticipated_start,
            preheating_callback=preheating_callback,
        )

        # THEN: Timer scheduler is called with correct parameters
        mock_timer_scheduler.schedule_timer.assert_called_once_with(
            anticipated_start,
            preheating_callback,
        )

    @pytest.mark.asyncio
    async def test_cancel_preheating_scheduler_calls_cancel_callback(
        self,
        use_case: SchedulePreheatingUseCase,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test that cancel_preheating_scheduler() calls the cancel callback.

        Verifies that a previously scheduled timer can be canceled.
        """
        # GIVEN: A timer has been scheduled
        cancel_callback = Mock()
        mock_timer_scheduler.schedule_timer.return_value = cancel_callback
        await use_case.create_preheating_scheduler(
            anticipated_start=datetime(2025, 2, 10, 10, 0, 0),
            preheating_callback=Mock(),
        )

        # WHEN: cancel_preheating_scheduler is called
        await use_case.cancel_preheating_scheduler()

        # THEN: The cancel callback is invoked
        cancel_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_preheating_scheduler_no_op_when_no_timer(
        self,
        use_case: SchedulePreheatingUseCase,
    ) -> None:
        """Test that cancel_preheating_scheduler() is safe when no timer exists.

        Verifies no exception is raised.
        """
        # WHEN: cancel_preheating_scheduler is called without scheduling
        await use_case.cancel_preheating_scheduler()

        # THEN: No exception is raised (no-op)
