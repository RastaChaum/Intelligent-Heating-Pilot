"""Recording extraction queue for incremental, configurable-period data loading.

This module implements a sequential, asynchronous extraction queue that loads
historical entity data from the Home Assistant Recorder one configurable period
at a time. This prevents overwhelming the Recorder and keeps Home Assistant
responsive during the initial cache population.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

try:
    from homeassistant.util import dt as dt_util
except ImportError:
    dt_util = None

from ...const import DEFAULT_TASK_RANGE_DAYS
from ...domain.value_objects.historical_data import HistoricalDataSet
from ...domain.value_objects.recording_extraction_task import (
    ExtractionTaskState,
    RecordingExtractionTask,
)

if TYPE_CHECKING:
    from ...domain.interfaces.heating_cycle_service_interface import IHeatingCycleService
    from ...domain.interfaces.historical_data_adapter_interface import IHistoricalDataAdapter
    from ...domain.value_objects.heating import HeatingCycle

_LOGGER = logging.getLogger(__name__)

QUEUE_YIELD_SECONDS = 10.0


class RecordingExtractionQueue:
    """Queue-based orchestrator for incremental Recorder data extraction.

    This service manages asynchronous extraction of historical entity data
    from the Home Assistant Recorder, processing one configurable period at
    a time to:
    1. Prevent timeout/freezing of Home Assistant during large queries
    2. Load data incrementally into cache (progressive model availability)
    3. Respect the RecorderAccessQueue serialization (avoid concurrent access)

    The extraction period length is configurable via `task_range_days` to allow
    users to tune the load according to their machine's capabilities.

    Lifecycle:
    - populate_queue(start_date, end_date): Create extraction tasks
    - run_queue(): Execute tasks sequentially in the background
    - cancel_queue(): Stop ongoing extraction
    - get_progress(): Query extraction status

    The extracted cycles are passed to a callback function for progressive
    cache population (do NOT wait for all extraction to complete before
    building ML models).
    """

    def __init__(
        self,
        device_id: str,
        entity_id: str,
        historical_adapters: list[IHistoricalDataAdapter],
        heating_cycle_service: IHeatingCycleService | None = None,
        on_cycles_extracted: Callable[[list[HeatingCycle]], Awaitable[None] | None] | None = None,
        on_period_explored: Callable[[date, date], Awaitable[None] | None] | None = None,
        task_range_days: int = DEFAULT_TASK_RANGE_DAYS,
    ) -> None:
        """Initialize the extraction queue.

        Args:
            device_id: IHP device identifier
            entity_id: Entity ID to extract data from (e.g. a climate or sensor entity)
            historical_adapters: List of adapters to fetch historical data
            heating_cycle_service: Service used to extract heating cycles from raw data
            on_cycles_extracted: Callback function called after each period's extraction
                                with the extracted cycles list
            on_period_explored: Callback called after each period is explored
                               with (start_date, end_date), regardless of cycle count
            task_range_days: Number of days covered by each extraction task.
                             Increase to reduce task count (less pauses, more data per query).
                             Decrease on low-powered machines. Default: 7.
        """
        self._device_id = device_id
        self._entity_id = entity_id
        self._historical_adapters = historical_adapters
        self._heating_cycle_service = heating_cycle_service
        self._on_cycles_extracted = on_cycles_extracted
        self._on_period_explored = on_period_explored

        if task_range_days < 1:
            raise ValueError(
                f"task_range_days must be at least 1 day for RecordingExtractionQueue; got {task_range_days}"
            )
        self._task_range_days = task_range_days

        self._queue: deque[RecordingExtractionTask] = deque()
        self._is_running = False
        self._extraction_start_date: date | None = None
        self._extraction_end_date: date | None = None
        self._extracted_count = 0
        self._failed_count = 0
        self._cancel_requested = False

        _LOGGER.debug(
            "Initialized RecordingExtractionQueue for device=%s, entity=%s, task_range_days=%d",
            device_id,
            entity_id,
            task_range_days,
        )

    async def populate_queue(self, start_date: date, end_date: date) -> int:
        """Populate the queue with extraction tasks covering the given date range.

        Creates one RecordingExtractionTask per period of `task_range_days` days.
        Does NOT start extraction (call run_queue() to start).

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Number of tasks created

        Raises:
            RuntimeError: If queue extraction is already running
        """
        _LOGGER.debug("Entering RecordingExtractionQueue.populate_queue")

        if self._is_running:
            _LOGGER.error("Cannot populate queue while extraction is running")
            raise RuntimeError("Cannot populate queue while extraction is running")

        self._extraction_start_date = start_date
        self._extraction_end_date = end_date
        self._extracted_count = 0
        self._failed_count = 0
        self._cancel_requested = False

        # Clear existing queue
        self._queue.clear()

        # Create tasks, each covering task_range_days days
        current_date = start_date
        task_count = 0
        while current_date <= end_date:
            period_end = min(current_date + timedelta(days=self._task_range_days - 1), end_date)
            task = RecordingExtractionTask(
                start_date=current_date,
                end_date=period_end,
                device_id=self._device_id,
                state=ExtractionTaskState.PENDING,
            )
            self._queue.append(task)
            task_count += 1
            current_date += timedelta(days=self._task_range_days)

        _LOGGER.info(
            "Populated extraction queue with %d tasks from %s to %s (period=%d days each)",
            task_count,
            start_date,
            end_date,
            self._task_range_days,
        )
        _LOGGER.debug("Exiting RecordingExtractionQueue.populate_queue")
        return task_count

    async def run_queue(self) -> None:
        """Execute all queued extraction tasks sequentially.

        This is an asynchronous, long-running operation. When awaited, it will
        process the entire queue (or until cancelled) before returning, while
        cooperatively yielding control to the event loop between tasks to keep
        Home Assistant responsive.

        Callers that must not be blocked until the queue completes should
        schedule this method as a background task, for example:

            asyncio.create_task(queue.run_queue())

        Extracted cycles for each period are passed to the callback function (if
        provided) for progressive cache population.
        Raises:
            RuntimeError: If extraction is already running
        """
        _LOGGER.debug("Entering RecordingExtractionQueue.run_queue")

        if self._is_running:
            _LOGGER.error("Extraction queue is already running")
            raise RuntimeError("Extraction queue is already running")

        self._is_running = True
        _LOGGER.info(
            "Starting extraction queue: %d tasks from %s to %s",
            len(self._queue),
            self._extraction_start_date,
            self._extraction_end_date,
        )

        # Yield once to ensure the task is visible as running before processing.
        await asyncio.sleep(0)

        try:
            while self._queue and not self._cancel_requested:
                # Get next task
                task = self._queue.popleft()

                _LOGGER.debug(
                    "Processing extraction task for period=%s to %s (task %d/%d)",
                    task.start_date,
                    task.end_date,
                    self._extracted_count + self._failed_count + 1,
                    self._extracted_count + self._failed_count + len(self._queue) + 1,
                )

                try:
                    # Extract data for this period
                    cycles = await self._extract_period(task.start_date, task.end_date)

                    self._extracted_count += 1
                    _LOGGER.info(
                        "Extraction completed for period=%s to %s: %d cycles extracted",
                        task.start_date,
                        task.end_date,
                        len(cycles),
                    )

                    # Callback to progressively feed cache (sync or async)
                    if self._on_cycles_extracted and cycles:
                        result = self._on_cycles_extracted(cycles)
                        if inspect.isawaitable(result):
                            await result

                    # Callback to track period as explored (even if empty)
                    if self._on_period_explored:
                        result = self._on_period_explored(task.start_date, task.end_date)
                        if inspect.isawaitable(result):
                            await result

                except Exception as exc:
                    self._failed_count += 1
                    _LOGGER.warning(
                        "Extraction failed for period=%s to %s: %s",
                        task.start_date,
                        task.end_date,
                        exc,
                    )

                    # Continue with next task despite failure
                    continue

                # Pause between tasks to let the Recorder breathe
                await asyncio.sleep(QUEUE_YIELD_SECONDS)

            if self._cancel_requested:
                _LOGGER.info("Extraction queue cancelled by user")
            else:
                _LOGGER.info(
                    "Extraction queue complete: %d extracted, %d failed",
                    self._extracted_count,
                    self._failed_count,
                )

        finally:
            self._is_running = False
            _LOGGER.debug("Exiting RecordingExtractionQueue.run_queue")

    async def cancel_queue(self) -> None:
        """Cancel ongoing extraction.

        Sets a flag to stop processing remaining tasks after the current
        task completes.
        """
        _LOGGER.debug("Entering RecordingExtractionQueue.cancel_queue")
        _LOGGER.info("Cancellation requested for extraction queue")
        self._cancel_requested = True
        _LOGGER.debug("Exiting RecordingExtractionQueue.cancel_queue")

    async def get_progress(self) -> tuple[int, int, bool]:
        """Get current extraction progress.

        Returns:
            A tuple of (extracted_count, total_count, is_running)
        """
        total_count = self._extracted_count + self._failed_count + len(self._queue)
        return self._extracted_count, total_count, self._is_running

    async def _extract_period(self, start_date: date, end_date: date) -> list[HeatingCycle]:
        """Extract historical data for a given period from the Recorder.

        Args:
            start_date: First day (inclusive) of the period to extract
            end_date: Last day (inclusive) of the period to extract

        Returns:
            List of extracted HeatingCycle objects for the period

        Raises:
            Exception: If extraction fails (will be caught by run_queue())
        """
        _LOGGER.debug(
            "Extracting data from Recorder for period=%s to %s, device=%s, entity=%s",
            start_date,
            end_date,
            self._device_id,
            self._entity_id,
        )

        if self._heating_cycle_service is None:
            raise RuntimeError("HeatingCycleService is required for extraction")

        try:
            # Create time window for this period using HA local timezone to avoid
            # midnight boundary shifts on non-UTC installations.
            local_tz = dt_util.get_default_time_zone() if dt_util is not None else timezone.utc
            start_time = datetime.combine(start_date, time.min).replace(tzinfo=local_tz)
            end_time = datetime.combine(end_date, time.max).replace(tzinfo=local_tz)

            combined_data: HistoricalDataSet = HistoricalDataSet(data={})

            for adapter in self._historical_adapters:
                try:
                    # Fetch all supported data keys in a single recorder query
                    adapter_data = await adapter.fetch_all_historical_data(
                        entity_id=self._entity_id,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    if adapter_data is not None and adapter_data.data:
                        for data_key, measurements in adapter_data.data.items():
                            if measurements:
                                if data_key not in combined_data.data:
                                    combined_data.data[data_key] = []
                                combined_data.data[data_key].extend(measurements)
                except Exception as exc:
                    _LOGGER.warning(
                        "Failed to fetch historical data from adapter for %s to %s: %s",
                        start_date,
                        end_date,
                        exc,
                    )
                    continue

            historical_data_set = HistoricalDataSet(data=combined_data.data)

            cycles = await self._heating_cycle_service.extract_heating_cycles(
                device_id=self._device_id,
                history_data_set=historical_data_set,
                start_time=start_time,
                end_time=end_time,
            )

            _LOGGER.debug(
                "Extracted %d cycles from Recorder for %s to %s",
                len(cycles),
                start_date,
                end_date,
            )

            return cycles

        except Exception as exc:
            _LOGGER.warning(
                "Failed to extract cycles for period %s to %s: %s",
                start_date,
                end_date,
                exc,
            )
            raise
