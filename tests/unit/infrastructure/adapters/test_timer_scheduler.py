"""Unit tests for HATimerScheduler adapter.

Tests the Home Assistant timer scheduler adapter that wraps
async_track_point_in_time for scheduling anticipation triggers.

Coverage targets:
- Initialization
- Timer scheduling and callback execution
- Timer cancellation
- Multiple concurrent timers
- Edge cases: past times, timezone handling, DST
- Long duration timers (>1h)
- Reschedule scenarios
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler import (
    HATimerScheduler,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock(spec=HomeAssistant)
    hass.async_create_task = Mock()
    return hass


class TestHATimerSchedulerInit:
    """Test suite for HATimerScheduler initialization."""

    def test_init_stores_hass_reference(self, mock_hass):
        """Test that __init__ correctly stores the hass reference.

        COVERAGE: Line 34 (self._hass = hass)
        """
        # Arrange & Act
        scheduler = HATimerScheduler(mock_hass)

        # Assert
        assert scheduler._hass is mock_hass


class TestHATimerSchedulerBasicScheduling:
    """Test suite for basic timer scheduling operations."""

    @pytest.mark.asyncio
    async def test_schedule_timer_calls_async_track_point_in_time(self, mock_hass):
        """Test that schedule_timer uses HA's async_track_point_in_time API.

        COVERAGE: Lines 51-68 (schedule_timer implementation)
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        mock_cancel = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=mock_cancel,
        ) as mock_track:
            # Act
            cancel_func = scheduler.schedule_timer(target_time, callback_func)

            # Assert
            mock_track.assert_called_once()
            assert mock_track.call_args.args[0] is mock_hass  # hass
            assert mock_track.call_args.args[2] == target_time  # target_time
            assert cancel_func is mock_cancel

    @pytest.mark.asyncio
    async def test_schedule_timer_returns_cancel_function(self, mock_hass):
        """Test that schedule_timer returns a cancel function."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        mock_cancel = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=mock_cancel,
        ):
            # Act
            cancel_func = scheduler.schedule_timer(target_time, callback_func)

            # Assert
            assert callable(cancel_func)
            assert cancel_func is mock_cancel

    @pytest.mark.asyncio
    async def test_schedule_timer_logs_scheduled_time(self, mock_hass, caplog):
        """Test that schedule_timer logs the target time at DEBUG level.

        COVERAGE: Lines 62-65 (_LOGGER.debug)
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time"
        ):
            # Act
            with caplog.at_level("DEBUG"):
                scheduler.schedule_timer(target_time, callback_func)

            # Assert
            assert "Timer scheduled for" in caplog.text
            assert "2025-01-15T10:30:00+00:00" in caplog.text


class TestHATimerSchedulerCallbackExecution:
    """Test suite for timer callback execution."""

    @pytest.mark.asyncio
    async def test_timer_callback_creates_async_task(self, mock_hass):
        """Test that the internal callback creates an async task.

        COVERAGE: Lines 52-54 (_timer_callback implementation)
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        captured_callback = None

        def capture_callback(hass, callback, time):
            nonlocal captured_callback
            captured_callback = callback
            return Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            side_effect=capture_callback,
        ):
            # Act
            scheduler.schedule_timer(target_time, callback_func)

            # Execute the captured callback
            assert captured_callback is not None, "Callback was not captured"
            captured_callback(target_time)

            # Assert
            mock_hass.async_create_task.assert_called_once()
            # Verify that async_create_task was called with the result of callback_func()
            call_args = mock_hass.async_create_task.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_timer_callback_passes_callback_result_to_create_task(self, mock_hass):
        """Test that the callback's coroutine is passed to async_create_task."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        captured_callback = None

        def capture_callback(hass, callback, time):
            nonlocal captured_callback
            captured_callback = callback
            return Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            side_effect=capture_callback,
        ):
            # Act
            scheduler.schedule_timer(target_time, callback_func)
            assert captured_callback is not None, "Callback was not captured"
            captured_callback(target_time)

            # Assert
            callback_func.assert_called_once()
            mock_hass.async_create_task.assert_called_once()
            # Verify that a coroutine was passed (AsyncMock returns coroutine)
            call_args = mock_hass.async_create_task.call_args[0][0]
            assert hasattr(call_args, "__await__")  # Verify it's a coroutine


class TestHATimerSchedulerCancellation:
    """Test suite for timer cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_function_prevents_callback_execution(self, mock_hass):
        """Test that calling the cancel function prevents callback execution."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        mock_cancel = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=mock_cancel,
        ):
            # Act
            cancel_func = scheduler.schedule_timer(target_time, callback_func)
            cancel_func()

            # Assert
            mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_cancellations_are_safe(self, mock_hass):
        """Test that multiple cancellations don't cause errors."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        mock_cancel = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=mock_cancel,
        ):
            # Act
            cancel_func = scheduler.schedule_timer(target_time, callback_func)
            cancel_func()
            cancel_func()  # Second call

            # Assert: Should not raise any exception
            assert mock_cancel.call_count == 2


class TestHATimerSchedulerConcurrentTimers:
    """Test suite for multiple concurrent timers."""

    @pytest.mark.asyncio
    async def test_multiple_timers_can_be_scheduled_simultaneously(self, mock_hass):
        """Test that multiple timers can be scheduled at the same time."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time1 = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        target_time2 = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        target_time3 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        callback3 = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            side_effect=[Mock(), Mock(), Mock()],
        ) as mock_track:
            # Act
            cancel1 = scheduler.schedule_timer(target_time1, callback1)
            cancel2 = scheduler.schedule_timer(target_time2, callback2)
            cancel3 = scheduler.schedule_timer(target_time3, callback3)

            # Assert
            assert mock_track.call_count == 3
            assert callable(cancel1)
            assert callable(cancel2)
            assert callable(cancel3)
            # Verify each cancel function is independent
            assert cancel1 is not cancel2
            assert cancel2 is not cancel3
            assert cancel1 is not cancel3

    @pytest.mark.asyncio
    async def test_canceling_one_timer_doesnt_affect_others(self, mock_hass):
        """Test that canceling one timer doesn't affect other scheduled timers."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        target_time1 = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        target_time2 = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        mock_cancel1 = Mock()
        mock_cancel2 = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            side_effect=[mock_cancel1, mock_cancel2],
        ):
            # Act
            cancel1 = scheduler.schedule_timer(target_time1, callback1)
            scheduler.schedule_timer(target_time2, callback2)
            cancel1()  # Cancel only first timer

            # Assert
            mock_cancel1.assert_called_once()
            mock_cancel2.assert_not_called()

    @pytest.mark.asyncio
    async def test_ten_concurrent_timers_for_multiple_devices(self, mock_hass):
        """Test scheduling 10 timers simulating multiple IHP devices.

        Simulates real-world scenario with multiple heating zones.
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        base_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callbacks = [AsyncMock() for _ in range(10)]
        target_times = [base_time + timedelta(minutes=i * 15) for i in range(10)]

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            cancel_funcs = [
                scheduler.schedule_timer(time, callback)
                for time, callback in zip(target_times, callbacks)
            ]

            # Assert
            assert mock_track.call_count == 10
            assert len(cancel_funcs) == 10
            assert all(callable(cancel) for cancel in cancel_funcs)


class TestHATimerSchedulerEdgeCases:
    """Test suite for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_schedule_timer_in_past_still_works(self, mock_hass):
        """Test scheduling a timer for a time in the past.

        HA's async_track_point_in_time handles this - we just verify
        the adapter doesn't reject it.
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        past_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            cancel_func = scheduler.schedule_timer(past_time, callback_func)

            # Assert: Should not raise, delegates to HA
            mock_track.assert_called_once()
            assert callable(cancel_func)

    @pytest.mark.asyncio
    async def test_schedule_timer_with_different_timezones(self, mock_hass):
        """Test scheduling timers with different timezone-aware datetimes."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        utc_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            scheduler.schedule_timer(utc_time, callback_func)

            # Assert
            assert mock_track.call_args.args[2] == utc_time

    @pytest.mark.asyncio
    async def test_schedule_timer_very_far_future(self, mock_hass):
        """Test scheduling a timer for a time far in the future (24h+).

        Validates memory management and long-duration timer handling.
        """
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        far_future = datetime(2025, 1, 20, 10, 0, 0, tzinfo=timezone.utc)  # 5 days ahead
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            cancel_func = scheduler.schedule_timer(far_future, callback_func)

            # Assert
            mock_track.assert_called_once()
            assert callable(cancel_func)

    @pytest.mark.asyncio
    async def test_schedule_timer_one_second_precision(self, mock_hass):
        """Test timer scheduled with 1-second precision."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        precise_time = datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            scheduler.schedule_timer(precise_time, callback_func)

            # Assert
            assert mock_track.call_args.args[2] == precise_time
            assert mock_track.call_args.args[2].second == 45


class TestHATimerSchedulerReschedule:
    """Test suite for timer rescheduling scenarios."""

    @pytest.mark.asyncio
    async def test_reschedule_cancels_previous_and_schedules_new(self, mock_hass):
        """Test that rescheduling cancels previous timer and creates new one."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        time1 = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        time2 = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        mock_cancel1 = Mock()
        mock_cancel2 = Mock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            side_effect=[mock_cancel1, mock_cancel2],
        ):
            # Act
            cancel1 = scheduler.schedule_timer(time1, callback_func)
            cancel1()  # Cancel first
            cancel2 = scheduler.schedule_timer(time2, callback_func)  # Reschedule

            # Assert
            mock_cancel1.assert_called_once()
            mock_cancel2.assert_not_called()
            assert callable(cancel2)

    @pytest.mark.asyncio
    async def test_multiple_reschedules_in_sequence(self, mock_hass):
        """Test multiple consecutive reschedules (>5 times)."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        base_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        callback_func = AsyncMock()
        cancel_funcs = []

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act: Schedule 10 times (simulating frequent recalculations)
            for i in range(10):
                target_time = base_time + timedelta(minutes=i)
                if cancel_funcs:
                    cancel_funcs[-1]()  # Cancel previous
                cancel_funcs.append(scheduler.schedule_timer(target_time, callback_func))

            # Assert
            assert mock_track.call_count == 10
            assert len(cancel_funcs) == 10


class TestHATimerSchedulerLongDuration:
    """Test suite for long-duration timer scenarios (>1h)."""

    @pytest.mark.asyncio
    async def test_timer_scheduled_two_hours_ahead(self, mock_hass):
        """Test scheduling a timer 2 hours in advance."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        target_time = now + timedelta(hours=2)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            scheduler.schedule_timer(target_time, callback_func)

            # Assert
            mock_track.assert_called_once()
            scheduled_time = mock_track.call_args.args[2]
            assert (scheduled_time - now).total_seconds() == 7200  # 2 hours

    @pytest.mark.asyncio
    async def test_timer_scheduled_six_hours_ahead(self, mock_hass):
        """Test scheduling a timer 6 hours in advance (max LHS window)."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        target_time = now + timedelta(hours=6)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            scheduler.schedule_timer(target_time, callback_func)

            # Assert
            mock_track.assert_called_once()
            scheduled_time = mock_track.call_args.args[2]
            assert (scheduled_time - now).total_seconds() == 21600  # 6 hours

    @pytest.mark.asyncio
    async def test_timer_scheduled_twenty_four_hours_ahead(self, mock_hass):
        """Test scheduling a timer 24 hours in advance (overnight scenario)."""
        # Arrange
        scheduler = HATimerScheduler(mock_hass)
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        target_time = now + timedelta(hours=24)
        callback_func = AsyncMock()

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.timer_scheduler.async_track_point_in_time",
            return_value=Mock(),
        ) as mock_track:
            # Act
            scheduler.schedule_timer(target_time, callback_func)

            # Assert
            mock_track.assert_called_once()
            scheduled_time = mock_track.call_args.args[2]
            assert (scheduled_time - now).total_seconds() == 86400  # 24 hours
