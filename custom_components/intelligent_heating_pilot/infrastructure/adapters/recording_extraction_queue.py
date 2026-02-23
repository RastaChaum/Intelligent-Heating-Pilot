"""Recording extraction queue for incremental daily data loading.

This module implements a sequential, asynchronous extraction queue that loads
climate and environment data from the Home Assistant Recorder one day at a time.
This prevents overwhelming the Recorder and keeps Home Assistant responsive during
the initial cache population.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ...domain.value_objects.recording_extraction_task import (
    ExtractionTaskState,
    RecordingExtractionTask,
)

if TYPE_CHECKING:
    from ...domain.interfaces.historical_data_adapter_interface import IHistoricalDataAdapter
    from ...domain.value_objects.heating import HeatingCycle

_LOGGER = logging.getLogger(__name__)


class RecordingExtractionQueue:
    """Queue-based orchestrator for incremental Recorder data extraction.

    This service manages asynchronous extraction of climate and environment data
    from the Home Assistant Recorder, processing one day at a time to:
    1. Prevent timeout/freezing of Home Assistant during large queries
    2. Load data incrementally into cache (progressive model availability)
    3. Respect the RecorderAccessQueue serialization (avoid concurrent access)

    Lifecycle:
    - populate_queue(start_date, end_date): Create daily extraction tasks
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
        climate_entity_id: str,
        historical_adapters: list[IHistoricalDataAdapter],
        on_cycles_extracted: Callable[[list[HeatingCycle]], None] | None = None,
    ) -> None:
        """Initialize the extraction queue.

        Args:
            device_id: IHP device identifier
            climate_entity_id: VTherm climate entity ID
            historical_adapters: List of adapters to fetch historical data
            on_cycles_extracted: Callback function called after each day's extraction
                                with the extracted cycles list
        """
        self._device_id = device_id
        self._climate_entity_id = climate_entity_id
        self._historical_adapters = historical_adapters
        self._on_cycles_extracted = on_cycles_extracted

        self._queue: deque[RecordingExtractionTask] = deque()
        self._is_running = False
        self._extraction_start_date: date | None = None
        self._extraction_end_date: date | None = None
        self._extracted_count = 0
        self._failed_count = 0
        self._cancel_requested = False

        _LOGGER.debug(
            "Initialized RecordingExtractionQueue for device=%s, climate=%s",
            device_id,
            climate_entity_id,
        )

    async def populate_queue(self, start_date: date, end_date: date) -> int:
        """Populate the queue with daily extraction tasks.

        Creates one RecordingExtractionTask per day in the date range.
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

        # Create daily tasks
        current_date = start_date
        task_count = 0
        while current_date <= end_date:
            task = RecordingExtractionTask(
                extraction_date=current_date,
                device_id=self._device_id,
                climate_entity_id=self._climate_entity_id,
                state=ExtractionTaskState.PENDING,
            )
            self._queue.append(task)
            task_count += 1
            current_date += timedelta(days=1)

        _LOGGER.info(
            "Populated extraction queue with %d daily tasks from %s to %s",
            task_count,
            start_date,
            end_date,
        )
        _LOGGER.debug("Exiting RecordingExtractionQueue.populate_queue")
        return task_count

    async def run_queue(self) -> None:
        """Execute all queued extraction tasks sequentially.

        This method runs asynchronously and does NOT block. Each day's extraction
        is performed one at a time, and extracted cycles are passed to the
        callback function (if provided) for progressive cache population.

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

        try:
            while self._queue and not self._cancel_requested:
                # Get next task
                task = self._queue.popleft()

                _LOGGER.debug(
                    "Processing extraction task for date=%s (task %d/%d)",
                    task.extraction_date,
                    self._extracted_count + self._failed_count + 1,
                    self._extracted_count + self._failed_count + len(self._queue) + 1,
                )

                try:
                    # Extract data for this day
                    cycles = await self._extract_day(task.extraction_date)

                    self._extracted_count += 1
                    _LOGGER.info(
                        "Extraction completed for date=%s: %d cycles extracted",
                        task.extraction_date,
                        len(cycles),
                    )

                    # Callback to progressively feed cache
                    if self._on_cycles_extracted and cycles:
                        self._on_cycles_extracted(cycles)

                except Exception as exc:
                    self._failed_count += 1
                    _LOGGER.warning(
                        "Extraction failed for date=%s: %s",
                        task.extraction_date,
                        exc,
                    )

                    # Continue with next task despite failure
                    continue

                # Small async checkpoint to let HA process other tasks
                await asyncio.sleep(0)

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

    async def _extract_day(self, extraction_date: date) -> list[HeatingCycle]:
        """Extract climate and environment data for a single day.

        This is a private method that performs the actual data extraction
        from Home Assistant adapters for one specific date.

        Args:
            extraction_date: Date to extract

        Returns:
            List of extracted heating cycles for the day

        Raises:
            ValueError: If extraction fails
        """
        _LOGGER.debug("Extracting data for date=%s", extraction_date)

        # Define extraction window: start of day to end of day
        start_time = datetime.combine(extraction_date, datetime.min.time())
        end_time = datetime.combine(
            extraction_date, datetime.max.time()
        )  # Note: This is placeholder - actual implementation will use adapters

        # Placeholder: actual extraction would call heating_cycle_service
        # after fetching historical data from adapters
        _LOGGER.debug(
            "Extracted data window: %s to %s", start_time.isoformat(), end_time.isoformat()
        )

        # Return empty list for now - actual cycles come from extract loop
        return []
