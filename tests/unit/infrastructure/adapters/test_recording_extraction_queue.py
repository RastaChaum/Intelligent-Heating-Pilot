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
    async def test_populate_queue_creates_weekly_tasks(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test that populate_queue creates one task per TASK_RANGE_DAYS window."""
        # GIVEN: 15-day range = ceil(15/7) = 3 weekly tasks
        start_date = date(2024, 1, 10)
        end_date = date(2024, 1, 24)

        # WHEN
        task_count = await extraction_queue.populate_queue(start_date, end_date)

        # THEN
        expected_count = 3  # Jan 10, Jan 17, Jan 24
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
        # GIVEN: First population (1 weekly task)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 7))

        # WHEN: Second population (3 weekly tasks: Jan 10, 17, 24)
        task_count = await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        # THEN: Should only have new tasks (3 weeks), not accumulated
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
        # GIVEN: 15-day range → 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # Should be in date order, one task per 7-day window
        expected_order = [
            date(2024, 1, 10),
            date(2024, 1, 17),
            date(2024, 1, 24),
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
        """Test that callback is invoked after each week's extraction."""
        # GIVEN: 15-day range → 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        # Make _extract_day return cycles for 2 of the 3 tasks
        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 10):
                return sample_heating_cycles[:1]
            elif extraction_date == date(2024, 1, 17):
                return sample_heating_cycles[1:]
            return []

        extraction_queue._extract_day = mock_extract_day
        mock_on_cycles_extracted.reset_mock()

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Callback should be called twice (for weeks with cycles)
        assert mock_on_cycles_extracted.call_count == 2

    @pytest.mark.asyncio
    async def test_run_queue_skips_callback_if_no_cycles_extracted(
        self,
        extraction_queue: RecordingExtractionQueue,
        mock_on_cycles_extracted: Mock,
    ) -> None:
        """Test that callback is not called when week has no cycles."""
        # GIVEN: Single weekly task
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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 3 weekly tasks
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 5 weekly tasks (Jan 1, 8, 15, 22, 29)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 29))

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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        # Manually set state
        extraction_queue._extracted_count = 2
        extraction_queue._failed_count = 1
        # Queue still has all 3 items (no extraction has run)

        # WHEN
        extracted, total, _ = await extraction_queue.get_progress()

        # THEN
        # Total = extracted_count + failed_count + queue_length = 2 + 1 + 3 = 6
        assert extracted == 2
        assert total == 6  # 2 extracted + 1 failed + 3 remaining in queue


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
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        failed_dates = []

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 17):
                failed_dates.append(extraction_date)
                raise ValueError("Extraction error for this week")
            return []

        extraction_queue._extract_day = mock_extract_day

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        # Should have processed all 3 weeks, 1 failed, 2 succeeded
        assert extraction_queue._extracted_count == 2
        assert extraction_queue._failed_count == 1
        assert failed_dates == [date(2024, 1, 17)]

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
        # 3 weekly tasks: Jan 10, Jan 17, Jan 24
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))
        await extraction_queue.run_queue()
        assert extraction_queue._extracted_count == 3

        # Second run: populate with different range (5 weekly tasks: Feb 1, 8, 15, 22, 29)
        await extraction_queue.populate_queue(date(2024, 2, 1), date(2024, 2, 29))
        await extraction_queue.run_queue()
        assert (
            extraction_queue._extracted_count == 5
        )  # counter reset on populate; 5 new extractions

    @pytest.mark.asyncio
    async def test_queue_state_after_cancellation(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Test queue state is consistent after cancellation."""
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        async def mock_extract_day(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 17):
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


# ============================================================================
# Critical Sequential Execution Tests (TDD Reinforcement)
# ============================================================================


class TestRecordingExtractionQueueSequentialityValidation:
    """Critical tests to VALIDATE true sequential execution (not just mocked order)."""

    @pytest.mark.asyncio
    async def test_sequential_execution_with_timing_verification(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Validate REAL sequential execution by tracking start and completion times.

        CRITICAL TEST: If implementation runs tasks in parallel, this will FAIL.
        Each task MUST complete before next one starts.
        """
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        execution_timeline = []

        async def mock_extract_with_timing(extraction_date: date) -> list[HeatingCycle]:
            """Track when each task starts and ends."""
            execution_timeline.append(("start", extraction_date))
            await asyncio.sleep(0.01)  # Simulate work (important for parallelism detection)
            execution_timeline.append(("end", extraction_date))
            return []

        extraction_queue._extract_day = mock_extract_with_timing

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Verify STRICT sequential pattern
        # Pattern MUST be: start_w1, end_w1, start_w2, end_w2, start_w3, end_w3
        # If parallel: start_w1, start_w2, start_w3, end_w1, end_w2, end_w3 ❌ FAILS THIS TEST
        expected_timeline = [
            ("start", date(2024, 1, 10)),
            ("end", date(2024, 1, 10)),
            ("start", date(2024, 1, 17)),
            ("end", date(2024, 1, 17)),
            ("start", date(2024, 1, 24)),
            ("end", date(2024, 1, 24)),
        ]
        assert execution_timeline == expected_timeline, (
            f"Tasks must be sequential (start→end→start→end→...). " f"Got: {execution_timeline}"
        )

    @pytest.mark.asyncio
    async def test_no_overlapping_task_execution(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify that no two tasks execute simultaneously (strict serialization).

        This detects if implementation uses asyncio.gather or similar parallel approaches.
        """
        # GIVEN: 3 weekly tasks (Jan 10, Jan 17, Jan 24)
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        active_tasks = []
        max_concurrent = 0

        async def mock_extract_track_concurrency(extraction_date: date) -> list[HeatingCycle]:
            nonlocal max_concurrent
            active_tasks.append(extraction_date)
            current_concurrent = len(active_tasks)
            max_concurrent = max(max_concurrent, current_concurrent)

            await asyncio.sleep(0.01)

            active_tasks.remove(extraction_date)
            return []

        extraction_queue._extract_day = mock_extract_track_concurrency

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Never more than 1 task active at a time
        assert max_concurrent == 1, (
            f"Tasks must NOT overlap. Maximum concurrent tasks was {max_concurrent}, " f"expected 1"
        )

    @pytest.mark.asyncio
    async def test_tasks_execute_in_queued_order(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify tasks execute in the exact order they were queued.

        This validates FIFO semantics: first populated task must execute first.
        """
        # GIVEN: 5 weekly tasks (Jan 1, 8, 15, 22, 29)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 29))

        execution_order = []

        async def mock_extract_track_order(extraction_date: date) -> list[HeatingCycle]:
            execution_order.append(extraction_date)
            return []

        extraction_queue._extract_day = mock_extract_track_order

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Exact order, not shuffled or randomized
        expected_order = [
            date(2024, 1, 1),
            date(2024, 1, 8),
            date(2024, 1, 15),
            date(2024, 1, 22),
            date(2024, 1, 29),
        ]
        assert execution_order == expected_order, (
            f"Tasks must execute in queue order (FIFO). "
            f"Expected: {expected_order}, Got: {execution_order}"
        )


# ============================================================================
# Callback Validation Tests (TDD Reinforcement)
# ============================================================================


class TestRecordingExtractionQueueCallbackValidation:
    """Critical tests to VALIDATE callback receives correct cycles with correct dates."""

    @pytest.mark.asyncio
    async def test_callback_receives_correct_cycles_for_each_date(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify callback receives the EXACT cycles extracted for each date.

        CRITICAL: Callback must NOT mix cycles from different dates.
        """
        callbacks_received = []

        def on_cycles(cycles: list[HeatingCycle]) -> None:
            """Track what cycles callback received (synchronous)."""
            callbacks_received.append(list(cycles))

        extraction_queue._on_cycles_extracted = on_cycles

        # GIVEN: Create mock cycles with date markers in their contents
        cycle_jan10_a = HeatingCycle(
            device_id="sensor.test_device",
            start_time=datetime(2024, 1, 10, 8, 0),
            end_time=datetime(2024, 1, 10, 9, 0),
            target_temp=21.0,
            end_temp=20.5,
            start_temp=18.0,
            tariff_details=None,
        )
        cycle_jan10_b = HeatingCycle(
            device_id="sensor.test_device",
            start_time=datetime(2024, 1, 10, 10, 0),
            end_time=datetime(2024, 1, 10, 11, 0),
            target_temp=21.0,
            end_temp=20.6,
            start_temp=18.5,
            tariff_details=None,
        )
        cycle_jan11 = HeatingCycle(
            device_id="sensor.test_device",
            start_time=datetime(2024, 1, 11, 8, 0),
            end_time=datetime(2024, 1, 11, 9, 0),
            target_temp=21.0,
            end_temp=20.7,
            start_temp=18.2,
            tariff_details=None,
        )

        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 17))

        async def mock_extract_returns_cycles(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date == date(2024, 1, 10):
                return [cycle_jan10_a, cycle_jan10_b]
            elif extraction_date == date(2024, 1, 17):
                return [cycle_jan11]
            return []

        extraction_queue._extract_day = mock_extract_returns_cycles

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Callback received correct cycles in order
        assert (
            len(callbacks_received) == 2
        ), f"Expected 2 callback invocations, got {len(callbacks_received)}"

        # First callback: Jan 10 cycles
        assert (
            len(callbacks_received[0]) == 2
        ), f"First callback should have 2 cycles, got {len(callbacks_received[0])}"
        assert callbacks_received[0][0] == cycle_jan10_a
        assert callbacks_received[0][1] == cycle_jan10_b

        # Second callback: Jan 11 cycles
        assert (
            len(callbacks_received[1]) == 1
        ), f"Second callback should have 1 cycle, got {len(callbacks_received[1])}"
        assert callbacks_received[1][0] == cycle_jan11

    @pytest.mark.asyncio
    async def test_callback_not_invoked_for_empty_extraction_days(
        self,
        extraction_queue: RecordingExtractionQueue,
        mock_on_cycles_extracted: Mock,
    ) -> None:
        """Verify callback is ONLY invoked when cycles are actually extracted.

        Days with no cycles should NOT trigger callback (empty list not passed).
        """
        await extraction_queue.populate_queue(date(2024, 1, 10), date(2024, 1, 24))

        async def mock_extract_sparse(extraction_date: date) -> list[HeatingCycle]:
            """Only second week (Jan 17) has cycles; others are empty."""
            if extraction_date == date(2024, 1, 17):
                return [
                    HeatingCycle(
                        device_id="sensor.test_device",
                        start_time=datetime(2024, 1, 17, 8, 0),
                        end_time=datetime(2024, 1, 17, 9, 0),
                        target_temp=21.0,
                        end_temp=20.5,
                        start_temp=18.0,
                        tariff_details=None,
                    )
                ]
            return []  # Jan 10 and Jan 24 weeks have no cycles

        extraction_queue._extract_day = mock_extract_sparse
        mock_on_cycles_extracted.reset_mock()

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Callback invoked exactly once (only for Jan 11)
        assert mock_on_cycles_extracted.call_count == 1, (
            f"Callback should be invoked for 1 day with cycles, "
            f"got {mock_on_cycles_extracted.call_count} invocations"
        )

        # Verify the call received 1 cycle
        call_args = mock_on_cycles_extracted.call_args[0]
        cycles_passed = call_args[0]
        assert len(cycles_passed) == 1


# ============================================================================
# Cancellation Validation Tests (TDD Reinforcement)
# ============================================================================


class TestRecordingExtractionQueueCancellationValidation:
    """Critical tests to VALIDATE cancellation truly stops the queue."""

    @pytest.mark.asyncio
    async def test_cancellation_stops_at_task_boundary(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify cancellation stops cleanly at task boundaries (no partial tasks).

        CRITICAL: Current task must complete, but no new task should start.
        """
        # GIVEN: 5 weekly tasks (Jan 1, 8, 15, 22, 29)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 29))

        task_executions = []

        async def mock_extract_cancel_on_third(extraction_date: date) -> list[HeatingCycle]:
            task_executions.append(extraction_date)

            # Request cancellation after third task
            if len(task_executions) == 3:
                await extraction_queue.cancel_queue()

            return []

        extraction_queue._extract_day = mock_extract_cancel_on_third

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Should have processed exactly 3 tasks before stopping
        assert len(task_executions) == 3, (
            f"Expected 3 tasks executed before cancellation, " f"got {len(task_executions)}"
        )
        assert task_executions == [date(2024, 1, 1), date(2024, 1, 8), date(2024, 1, 15)]

    @pytest.mark.asyncio
    async def test_cancellation_with_partial_extraction_preserves_count(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify extraction count is accurate even after cancellation.

        If 2 of 5 tasks completed before cancel, extracted_count must be 2.
        """
        # GIVEN: 5 weekly tasks (Jan 1, 8, 15, 22, 29)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 1, 29))

        processed = 0

        async def mock_extract_cancel_early(extraction_date: date) -> list[HeatingCycle]:
            nonlocal processed
            processed += 1

            # Request cancel after 2nd task
            if processed == 2:
                asyncio.create_task(extraction_queue.cancel_queue())

            return []

        extraction_queue._extract_day = mock_extract_cancel_early

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._extracted_count == 2, (
            f"Extracted count should be 2 (tasks completed before cancel), "
            f"got {extraction_queue._extracted_count}"
        )
        assert extraction_queue._failed_count == 0
        assert extraction_queue._cancel_requested is True


# ============================================================================
# Progress Tracking Accuracy Tests (TDD Reinforcement)
# ============================================================================


class TestRecordingExtractionQueueProgressAccuracy:
    """Critical tests to VALIDATE progress counters are accurate."""

    @pytest.mark.asyncio
    async def test_progress_total_count_accuracy_during_extraction(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify total count remains accurate throughout extraction.

        total = extracted + failed + remaining_in_queue
        """
        # GIVEN: 6 weekly tasks (Jan 1, 8, 15, 22, 29, Feb 5)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 2, 5))

        async def mock_extract_simple(extraction_date: date) -> list[HeatingCycle]:
            # Simple mock that returns empty cycles
            return []

        extraction_queue._extract_day = mock_extract_simple

        # WHEN
        await extraction_queue.run_queue()

        # THEN: Verify final state is accurate
        extracted, total, is_running = await extraction_queue.get_progress()

        # All 6 tasks should be extracted (6 extracted + 0 failed + 0 remaining = 6 total)
        assert extracted == 6, f"Expected 6 extracted tasks, got {extracted}"
        assert total == 6, f"Expected total count of 6, got {total}"
        assert is_running is False, "Queue should not be running after completion"

        # Verify counters directly
        assert extraction_queue._extracted_count == 6
        assert extraction_queue._failed_count == 0

    @pytest.mark.asyncio
    async def test_progress_count_survives_partial_failures(
        self, extraction_queue: RecordingExtractionQueue
    ) -> None:
        """Verify progress is accurate when some extractions fail.

        GIVEN: 6 weekly tasks, 2 fail
        EXPECTED: extracted=4, failed=2, total=6
        """
        # GIVEN: 6 weekly tasks (Jan 1, 8, 15, 22, 29, Feb 5)
        await extraction_queue.populate_queue(date(2024, 1, 1), date(2024, 2, 5))

        failure_dates = {date(2024, 1, 8), date(2024, 1, 29)}

        async def mock_extract_with_failures(extraction_date: date) -> list[HeatingCycle]:
            if extraction_date in failure_dates:
                raise ValueError(f"Extraction failed for {extraction_date}")
            return []

        extraction_queue._extract_day = mock_extract_with_failures

        # WHEN
        await extraction_queue.run_queue()

        # THEN
        assert extraction_queue._extracted_count == 4, (
            f"Expected 4 successful extractions, " f"got {extraction_queue._extracted_count}"
        )
        assert extraction_queue._failed_count == 2, (
            f"Expected 2 failed extractions, " f"got {extraction_queue._failed_count}"
        )

        # Progress should reflect this
        extracted, total, is_running = await extraction_queue.get_progress()
        assert extracted == 4
        assert total == 6  # 4 + 2 + 0
        assert is_running is False
