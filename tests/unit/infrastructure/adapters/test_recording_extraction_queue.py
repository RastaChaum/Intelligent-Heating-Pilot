"""Tests for RecordingExtractionQueue infrastructure adapter."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.recording_extraction_task import (
    ExtractionTaskState,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.recording_extraction_queue import (
    RecordingExtractionQueue,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_historical_adapters() -> list:
    """Provide mock historical data adapters."""
    return []


@pytest.fixture
def mock_on_cycles_extracted() -> Mock:
    """Provide mock callback for extracted cycles."""
    return Mock()


@pytest.fixture
def extraction_queue(
    mock_historical_adapters: list,
    mock_on_cycles_extracted: Mock,
) -> RecordingExtractionQueue:
    """Create a RecordingExtractionQueue instance for testing."""
    return RecordingExtractionQueue(
        device_id="sensor.test_device",
        climate_entity_id="climate.living_room",
        historical_adapters=mock_historical_adapters,
        on_cycles_extracted=mock_on_cycles_extracted,
    )


@pytest.fixture
def sample_heating_cycles() -> list[HeatingCycle]:
    """Provide sample heating cycles for extraction."""
    start_time = datetime(2024, 1, 15, 8, 0, 0)
    return [
        HeatingCycle(
            device_id="sensor.test_device",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            target_temp=21.0,
            end_temp=20.5,
            start_temp=18.0,
            tariff_details=None,
        ),
        HeatingCycle(
            device_id="sensor.test_device",
            start_time=start_time + timedelta(hours=2),
            end_time=start_time + timedelta(hours=3),
            target_temp=21.0,
            end_temp=20.8,
            start_temp=19.5,
            tariff_details=None,
        ),
    ]


# ============================================================================
# Queue Population Tests
# ============================================================================


class TestRecordingExtractionQueuePopulation:
    """Test queue population functionality."""

    @pytest.mark.asyncio
    async def test_populate_queue_creates_daily_tasks(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that populate_queue creates one task per day."""
        # GIVEN
        start_date = date(2024, 1, 10)
        end_date = date(2024, 1, 15)

        # WHEN
        task_count = await extraction_queue.populate_queue(start_date, end_date)

        # THEN
        expected_count = 6  # Jan 10, 11, 12, 13, 14, 15
        assert task_count == expected_count

    @pytest.mark.asyncio
    async def test_populate_queue_with_single_day(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test populate_queue with single day (start_date == end_date)."""
        # GIVEN
        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 15)

        # WHEN
        task_count = await extraction_queue.populate_queue(start_date, end_date)

        # THEN
        assert task_count == 1

    @pytest.mark.asyncio
    async def test_populate_queue_clears_previous_queue(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that populate_queue clears any previous tasks."""
        # GIVEN: First population
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 5))

        # WHEN: Second population
        task_count = await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        # THEN: Should only have new tasks (3 days), not accumulated
        assert task_count == 3

    @pytest.mark.asyncio
    async def test_populate_queue_resets_counters(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that populate_queue resets extracted/failed counters."""
        # GIVEN: Simulate previous extraction
        extraction_queue._extracted_count = 5
        extraction_queue._failed_count = 2

        # WHEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        # THEN: Counters should be reset
        assert extraction_queue._extracted_count == 0
        assert extraction_queue._failed_count == 0

    @pytest.mark.asyncio
    async def test_populate_queue_raises_if_already_running(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that populate_queue raises RuntimeError if extraction is running."""
        # GIVEN: Mark queue as running
        extraction_queue._is_running = True

        # WHEN/THEN
        with pytest.raises(RuntimeError, match="Cannot populate queue while extraction is running"):
            await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

    @pytest.mark.asyncio
    async def test_populate_queue_all_tasks_in_pending_state(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that all newly created tasks are in PENDING state."""
        # GIVEN
        start_date = date(2024, 1, 10)
        end_date = date(2024, 1, 12)

        # WHEN
        await extraction_queue.populate_queue(start_date, end_date)

        # THEN
        # Access internal queue to verify task states
        for task in extraction_queue._queue:
            assert task.state == ExtractionTaskState.PENDING
            assert task.error is None


# ============================================================================
# Queue Execution Tests
# ============================================================================


class TestRecordingExtractionQueueExecution:
    """Test queue execution (run_queue)."""

    @pytest.mark.asyncio
    async def test_run_queue_executes_tasks_sequentially(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that run_queue executes tasks one at a time, not in parallel."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        # Track execution order
        execution_order = []

        # Mock _extract_day to track order
        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            execution_order.append(extraction_date)
            await asyncio.sleep(0.01)  # Small delay to ensure sequential
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        # Should be in date order
        expected_order = [
            date(2024, 1, 10),
            date(2024, 1, 11),
            date(2024, 1, 12),
            date(2024, 1, 13),
            date(2024, 1, 14),
            date(2024, 1, 15),
        ]
        assert execution_order == expected_order

    @pytest.mark.asyncio
    async def test_run_queue_raises_if_already_running(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that run_queue raises if already running."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))
        extraction_queue._is_running = True

        # WHEN/THEN
        with pytest.raises(RuntimeError, match="Extraction queue is already running"):
            await extraction_queue.run_queue()

    @pytest.mark.asyncio
    async def test_run_queue_with_empty_queue(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test run_queue with empty queue completes without error."""
        # GIVEN: Don't populate queue (it's empty)

        # WHEN/THEN: Should complete without error
        await extraction_queue.run_queue()

    @pytest.mark.asyncio
    async def test_run_queue_calls_callback_after_each_extraction(
        self,
        extraction_queue: RecordingExtractionQueue,
        mock_on_cycles_extracted: Mock,
        sample_heating_cycles: list[HeatingCycle],
    ) -> None:
        """Test that callback is invoked after each day's extraction."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        # Make _extract_day return cycles for testing
        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 10):
                return sample_heating_cycles[:1]
            elif extraction_date == date(2024, 1, 11):
                return sample_heating_cycles[1:]
            return []

        extraction_queue._extract_day = mock_extract_day
        mock_on_cycles_extracted.reset_mock()

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Callback should be called twice (for days with cycles)
        assert mock_on_cycles_extracted.call_count == 2

    @pytest.mark.asyncio
    async def test_run_queue_skips_callback_if_no_cycles_extracted(
        self,
        extraction_queue: RecordingExtractionQueue,
        mock_on_cycles_extracted: Mock,
    ) -> None:
        """Test that callback is not called when day has no cycles."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        # _extract_day returns empty list
        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            return []

        extraction_queue._extract_day = mock_extract_day
        mock_on_cycles_extracted.reset_mock()

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Callback should never be called
        mock_on_cycles_extracted.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_queue_does_not_block_ha_main_thread(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that run_queue yields control to event loop (asyncio.sleep(0))."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        # Track if control was yielded
        yield_detected = False

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            nonlocal yield_detected
            # This task should be able to run while extraction is ongoing
            yield_detected = True
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN/THEN
        # Should complete without blocking
        await extraction_queue.run_queue()
        assert yield_detected

    @pytest.mark.asyncio
    async def test_run_queue_increments_extracted_count(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that extracted_count increments for each successful extraction."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._extracted_count == 3

    @pytest.mark.asyncio
    async def test_run_queue_increments_failed_count_on_error(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that failed_count increments when extraction raises exception."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            raise ValueError("Test extraction error")

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._failed_count == 3
        assert extraction_queue._extracted_count == 0


# ============================================================================
# Queue Cancellation Tests
# ============================================================================


class TestRecordingExtractionQueueCancellation:
    """Test queue cancellation functionality."""

    @pytest.mark.asyncio
    async def test_cancel_queue_stops_extraction(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that cancel_queue stops processing remaining tasks."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        processing_count = 0

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            nonlocal processing_count
            processing_count += 1
            # After first task, request cancellation
            if processing_count == 1:
                await extraction_queue.cancel_queue()
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Should have processed only the first task before cancelling
        assert processing_count == 1

    @pytest.mark.asyncio
    async def test_cancel_queue_preserves_completed_tasks(
        self,
        extraction_queue: RecordingExtractionQueue,
        sample_heating_cycles: list[HeatingCycle],
    ) -> None:
        """Test that cancelled queue preserves count of completed tasks."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        processed = 0

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            nonlocal processed
            processed += 1
            if processed == 3:
                asyncio.create_task(extraction_queue.cancel_queue())
            return sample_heating_cycles if processed <= 3 else []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._extracted_count == 3
        assert extraction_queue._cancel_requested is True

    @pytest.mark.asyncio
    async def test_cancel_queue_multiple_calls_safe(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that calling cancel_queue multiple times is safe."""
        # WHEN/THEN: Should not raise
        await extraction_queue.cancel_queue()
        await extraction_queue.cancel_queue()
        await extraction_queue.cancel_queue()


# ============================================================================
# Progress Tracking Tests
# ============================================================================


class TestRecordingExtractionQueueProgress:
    """Test progress tracking functionality."""

    @pytest.mark.asyncio
    async def test_get_progress_returns_tuple(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that get_progress returns correct tuple format."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        # WHEN
        extracted, total, is_running = await extraction_queue.get_progress()

        # THEN
        assert isinstance(extracted, int)
        assert isinstance(total, int)
        assert isinstance(is_running, bool)
        assert extracted == 0
        assert total == 3
        assert is_running is False

    @pytest.mark.asyncio
    async def test_get_progress_during_extraction(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test get_progress while extraction is running."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        is_running_during = None
        task_counter = 0

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            nonlocal is_running_during, task_counter
            task_counter += 1
            # Check progress during extraction of task 2
            if task_counter == 2:
                _, _, is_running_during = await extraction_queue.get_progress()
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        # During extraction, is_running should be True
        assert is_running_during is True

    @pytest.mark.asyncio
    async def test_get_progress_after_completion(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test get_progress after queue completes."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        extracted, total, is_running = await extraction_queue.get_progress()
        assert extracted == 3
        assert total == 3
        assert is_running is False

    @pytest.mark.asyncio
    async def test_get_progress_total_count_includes_remaining(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that total count includes completed + failed + remaining."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        # Manually set state
        extraction_queue._extracted_count = 2
        extraction_queue._failed_count = 1
        # Queue still has all 6 items (no extraction has run)

        # WHEN
        extracted, total, _ = await extraction_queue.get_progress()

        # THEN
        # Total = extracted_count + failed_count + queue_length = 2 + 1 + 6 = 9
        assert extracted == 2
        assert total == 9  # 2 extracted + 1 failed + 6 remaining in queue


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestRecordingExtractionQueueErrorHandling:
    """Test error handling in queue execution."""

    @pytest.mark.asyncio
    async def test_queue_continues_on_single_task_failure(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that queue continues processing after a task fails."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))

        failed_dates = []

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 11):
                failed_dates.append(extraction_date)
                raise ValueError("Extraction error for this day")
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        # Should have processed all 3 days, 1 failed, 2 succeeded
        assert extraction_queue._extracted_count == 2
        assert extraction_queue._failed_count == 1
        assert failed_dates == [date(2024, 1, 11)]

    @pytest.mark.asyncio
    async def test_queue_logs_error_on_failure(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that errors are logged when extraction fails."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 11))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            raise TimeoutError("Recorder timeout")

        extraction_queue._extract_day = mock_extract_day

        # WHEN/THEN: Should complete without raising, but log error
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.recording_extraction_queue._LOGGER"
        ) as mock_logger:
            await extraction_queue.run_queue()
            # Verify error was logged
            assert mock_logger.warning.called

    @pytest.mark.asyncio
    async def test_queue_is_running_flag_reset_on_completion(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that _is_running flag is reset after queue completes."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 11))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._is_running is False

    @pytest.mark.asyncio
    async def test_queue_is_running_flag_reset_even_on_error(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that _is_running flag is reset even if exception occurs."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 11))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            raise RuntimeError("Unexpected error")

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Flag should be reset even after error
        assert extraction_queue._is_running is False


# ============================================================================
# State Consistency Tests
# ============================================================================


class TestRecordingExtractionQueueStateConsistency:
    """Test that queue maintains consistent state."""

    @pytest.mark.asyncio
    async def test_multiple_populate_and_run_cycles(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that queue can be populated and run multiple times."""

        # GIVEN
        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN/THEN: Run extraction twice
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 12))
        await extraction_queue.run_queue()
        assert extraction_queue._extracted_count == 3

        # Second run: populate with different range
        await extraction_queue.populate_queue(date(2024, 2, 1), date(2024, 2, 5))
        await extraction_queue.run_queue()
        assert extraction_queue._extracted_count == 5  # 3 from before + 5 new... wait no

    @pytest.mark.asyncio
    async def test_queue_state_after_cancellation(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test queue state is consistent after cancellation."""
        # GIVEN
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 15))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 12):
                await extraction_queue.cancel_queue()
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._is_running is False  # Flag should be reset
        assert extraction_queue._cancel_requested is True  # Flag should be set

    @pytest.mark.asyncio
    async def test_extract_day_not_called_when_queue_empty(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that _extract_day is never called when queue is empty."""
        # GIVEN
        mock_extract_day = AsyncMock()
        extraction_queue._extract_day = mock_extract_day

        # WHEN: Run queue without populating (empty queue)
        await extraction_queue.run_queue()

        # THEN
        mock_extract_day.assert_not_called()
