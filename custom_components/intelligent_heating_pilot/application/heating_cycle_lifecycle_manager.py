"""Lifecycle manager for heating cycle extraction."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, cast

from ..domain.interfaces.device_config_reader_interface import DeviceConfig
from ..domain.interfaces.heating_cycle_service_interface import IHeatingCycleService
from ..domain.services.extraction_date_range_calculator import ExtractionDateRangeCalculator
from ..domain.value_objects.heating import HeatingCycle
from ..domain.value_objects.historical_data import HistoricalDataKey, HistoricalDataSet
from ..infrastructure.adapters.recording_extraction_queue import RecordingExtractionQueue

if TYPE_CHECKING:
    from ..domain.interfaces import (
        IHeatingCycleStorage,
        IHistoricalDataAdapter,
        ILhsStorage,
        ITimerScheduler,
    )
    from .lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)

# Maximum number of entries in in-memory cycle cache before eviction
MAX_MEMORY_CACHE_ENTRIES = 50

try:
    from homeassistant.util import dt as dt_util
except ImportError:
    dt_util = None  # For testing without HA


class HeatingCycleLifecycleManager:
    """Manage heating cycle extraction lifecycle and refresh scheduling.

    This manager is a singleton per IHP device (identified by device_id).
    It orchestrates:
    1. In-memory cache management (_cached_cycles_for_target_time)
    2. Persistent storage via IHeatingCycleStorage and ILhsStorage
    3. Periodic refresh scheduling (24h timer)
    4. Cascade updates to LhsLifecycleManager when cycles change

    Architecture:
    - **In-memory cache**: Fast lookups for repeated queries (same device/date)
    - **Storage cache (IHeatingCycleStorage)**: Persistent incremental cycle storage
    - **Model storage (ILhsStorage)**: Long-term persistence of individual cycles
    - **Cascade to LHS**: When cycles update, triggers LHS recalculation

    Lifecycle Events:
    - refresh_heating_cycle_cache(): Initial load / periodic refresh, schedule 24h timer, cascade LHS update
    - on_retention_change(): Prune stale cycles, reload LHS, cascade LHS update
    - cancel(): Cleanup timers and release resources
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        heating_cycle_service: IHeatingCycleService,
        historical_adapters: list[IHistoricalDataAdapter],
        heating_cycle_storage: IHeatingCycleStorage | None,
        timer_scheduler: ITimerScheduler | None,
        lhs_storage: ILhsStorage | None,
        lhs_lifecycle_manager: LhsLifecycleManager | None,
        dead_time_updated_callback: Callable[[float], None] | None = None,
        extraction_semaphore: asyncio.Semaphore | None = None,
        on_extraction_complete_callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the lifecycle manager.

        Note: This should be instantiated via HeatingCycleLifecycleManagerFactory
        to ensure singleton behavior per device_id.

        Args:
            device_config: Device configuration data (includes retention settings).
            heating_cycle_service: Domain service for extracting heating cycles.
            historical_adapters: Infrastructure adapters for loading historical sensor data.
            heating_cycle_storage: Optional persistent cache for incremental cycle storage.
            timer_scheduler: Optional scheduler for periodic 24h refresh tasks.
            lhs_storage: Optional persistent storage for individual cycle records.
            lhs_lifecycle_manager: Optional LHS manager for cascade updates when cycles change.
            extraction_semaphore: Optional global semaphore to limit concurrent extractions (OOM prevention).
            on_extraction_complete_callback: Optional callback fired after cycle extraction completes.
        """
        self._device_config = device_config
        self._heating_cycle_service = heating_cycle_service
        self._historical_adapters = historical_adapters
        self._heating_cycle_storage = heating_cycle_storage
        self._timer_scheduler = timer_scheduler
        self._lhs_storage = lhs_storage
        self._lhs_lifecycle_manager = lhs_lifecycle_manager
        self._dead_time_updated_callback = dead_time_updated_callback
        self._extraction_semaphore = extraction_semaphore
        self._on_extraction_complete_callback = on_extraction_complete_callback

        # In-memory cache for fast repeated lookups
        # Key: (device_id, target_date) → list[HeatingCycle]
        # This avoids re-extracting cycles from storage/history for the same device/date
        self._cached_cycles_for_target_time: dict[tuple[str, date], list[HeatingCycle]] = {}
        self._timer_cancel_func: Callable[[], None] | None = None

        # Extraction queues for asynchronous incremental Recorder loading.
        # One queue is created per missing date range; _extraction_queue is kept
        # as a backward-compat alias pointing to the last created queue.
        self._extraction_queues: list[RecordingExtractionQueue] = []
        self._extraction_queue: RecordingExtractionQueue | None = None
        self._extraction_task: asyncio.Task | None = None

    async def refresh_heating_cycle_cache(self) -> None:
        """Refresh the heating cycle cache and schedule the next 24h timer.

        This is the single lifecycle entry point for both initial startup and
        periodic 24h refresh. It performs the same cache-aware, async-only
        extraction regardless of whether it is called at boot or from a timer.

        Lifecycle Event Flow:
        1. Schedule next 24h timer at dt_util.now() + 24H
        2. Calculate extraction window: start = now - retention_days, end = yesterday
        3. Find missing date ranges vs current cache
        4. Launch async extraction only for missing ranges
        5. Prune cycles outside the retention window from persistent storage

        Cycles are delivered asynchronously via the _on_cycles_extracted() callback.

        Returns:
            None
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.refresh_heating_cycle_cache")
        _LOGGER.info(
            "Heating cycle cache refresh triggered for device=%s", self._device_config.device_id
        )

        # Step 1: Cancel previous timer, then schedule next one at dt_util.now() + 24H
        if self._timer_cancel_func is not None:
            try:
                self._timer_cancel_func()
                _LOGGER.debug("Cancelled previous 24h refresh timer")
            except Exception as exc:
                _LOGGER.warning("Error cancelling previous timer: %s", exc)
            self._timer_cancel_func = None

        if self._timer_scheduler is not None:
            now = dt_util.now() if dt_util is not None else datetime.now()
            next_refresh = now + timedelta(hours=24)
            self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                next_refresh, self.trigger_24h_refresh
            )
            _LOGGER.debug("Scheduled 24h cycle refresh timer for %s", next_refresh.isoformat())

        # Step 2: Calculate startup window (most recent task_range_days only).
        # Backfill of older periods happens progressively via trigger_24h_refresh().
        start_date, end_date = self._calculate_startup_window()
        _LOGGER.debug("Extraction window: %s to %s", start_date, end_date)

        # Step 3: Prune cycles outside the retention window from persistent storage.
        # Pruning happens BEFORE extraction to avoid concurrent storage mutations.
        # LHS recalculation only runs when cycles were actually removed: on a normal
        # restart the model_storage values are already correct from the previous session,
        # so recalculating unconditionally would generate dozens of Store.async_save()
        # calls per device at startup — causing event loop saturation with 8+ devices.
        if self._heating_cycle_storage is not None:
            now = dt_util.now() if dt_util is not None else datetime.now()
            pruned = await self._heating_cycle_storage.prune_old_cycles(
                self._device_config.device_id, now
            )

            if pruned:
                _LOGGER.debug("Cycles pruned — recalculating LHS and dead time")
                try:
                    cache_data = await self._heating_cycle_storage.get_cache_data(
                        self._device_config.device_id
                    )
                    remaining_cycles: list[HeatingCycle] = (
                        list(cache_data.cycles) if cache_data is not None else []
                    )
                except Exception as exc:
                    _LOGGER.warning("Error loading remaining cycles for LHS recalculation: %s", exc)
                    remaining_cycles = []

                if remaining_cycles:
                    await self._trigger_lhs_cascade(remaining_cycles)
                    await self._persist_learned_dead_time(remaining_cycles)
                    _LOGGER.debug(
                        "Recalculated LHS and dead time from %d remaining cycles after pruning",
                        len(remaining_cycles),
                    )
                else:
                    _LOGGER.debug("All cycles pruned — skipping LHS recalculation")
            else:
                _LOGGER.debug(
                    "No cycles pruned — skipping LHS recalculation (model_storage already up to date)"
                )

        # Step 4: Find missing date ranges vs current (pruned) cache
        missing_ranges = await self._find_missing_date_ranges(start_date, end_date)

        # Step 5: Launch async extraction for missing ranges only
        if missing_ranges:
            await self._launch_extraction_for_ranges(missing_ranges)
            _LOGGER.info(
                "Cache refresh: launched async extraction for %d missing range(s)",
                len(missing_ranges),
            )
        else:
            _LOGGER.info("Cache refresh: cache is up to date, no extraction needed")

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.refresh_heating_cycle_cache")

    async def on_retention_change(self, new_retention_days: int) -> None:
        """Handle retention configuration changes.

        Updates the device config with the new retention period, invalidates the
        in-memory cache, then delegates all further processing (pruning, LHS
        recalculation, missing-range extraction) to refresh_heating_cycle_cache().

        Args:
            new_retention_days: Updated retention window in days.

        Returns:
            None
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.on_retention_change")
        _LOGGER.info("Retention changed to %d days", new_retention_days)

        # Step 1: Update device config retention (immutable, create new instance)
        self._device_config = DeviceConfig(
            device_id=self._device_config.device_id,
            vtherm_entity_id=self._device_config.vtherm_entity_id,
            scheduler_entities=self._device_config.scheduler_entities,
            lhs_retention_days=new_retention_days,
        )

        # Step 2: Clear in-memory cache (retention change invalidates all cached data)
        self._cached_cycles_for_target_time = {}
        _LOGGER.debug("Invalidated cycles in-memory cache due to retention change")

        # Step 3: Delegate to refresh — it handles pruning, LHS recalculation and
        # async extraction of missing date ranges for the new retention window.
        await self.refresh_heating_cycle_cache()

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.on_retention_change")

    async def get_cycles_for_window(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Return heating cycles for a specific time window.

        Cache Strategy (read-only operation):
        - **Reads from memory**: Not used (no time-based caching for arbitrary windows)
        - **Reads from storage**: Tries cycle_cache.get_cache_data() first
        - **Falls back to extraction**: If no cache, extracts from historical data
        - **Does NOT write**: This is a read-only operation, use update_cycles_for_window() to persist

        Args:
            device_id: Device identifier used for history queries and cache keys.
            start_time: Start of the query window.
            end_time: End of the query window.

        Returns:
            Heating cycles matching the requested window (filtered from cache or fresh extraction).
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.get_cycles_for_window")
        _LOGGER.debug("Getting cycles for device=%s from %s to %s", device_id, start_time, end_time)

        # Check inverted time range
        if start_time > end_time:
            _LOGGER.error("Invalid time range: start_time > end_time")
            raise ValueError("start_time must be before or equal to end_time")

        # Try to get from cache first
        if self._heating_cycle_storage is not None:
            cache_data = await self._heating_cycle_storage.get_cache_data(device_id)
            if cache_data is not None:
                # Filter cycles within the requested window
                cycles = [
                    cycle
                    for cycle in cache_data.cycles
                    if start_time <= cycle.start_time <= end_time
                ]
                _LOGGER.debug("Returning %d cycles from cache", len(cycles))
                _LOGGER.debug("Exiting HeatingCycleLifecycleManager.get_cycles_for_window")
                return cycles

        # No cache available — return empty list.
        # Only background refresh (RecordingExtractionQueue) queries the Recorder.
        # Event-driven callers must work from cache only (Rule 5).
        _LOGGER.debug(
            "No cache data for device=%s, returning empty cycles "
            "(Recorder queries only allowed from background refresh)",
            device_id,
        )
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.get_cycles_for_window")
        return []

    async def get_cycles_for_target_time(
        self,
        device_id: str,
        target_time: datetime,
    ) -> list[HeatingCycle]:
        """Return heating cycles within retention for a target time.

        Cache Strategy (optimized for repeated queries):
        - **Reads from memory first**: Checks _cached_cycles_for_target_time[(device_id, date)]
        - **On memory cache hit**: Returns immediately (fast path)
        - **On memory cache miss**: Calls get_cycles_for_window() which reads from storage
        - **Writes to memory**: Caches result in _cached_cycles_for_target_time for future calls
        - **Does NOT write to storage**: Uses get_cycles_for_window() which is read-only

        Use Case:
        This method is optimized for when the same device/date is queried multiple times
        (e.g., multiple predictions for the same day). Results are cached in memory for speed.

        Args:
            device_id: Device identifier used for history queries and cache keys.
            target_time: Target datetime used to derive the retention window.

        Returns:
            Heating cycles within the retention window [target_time - retention_days, target_time].
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.get_cycles_for_target_time")
        _LOGGER.debug("Getting cycles for device=%s at target_time=%s", device_id, target_time)

        # Create cache key using device_id and target date for time-based caching
        cache_key = (device_id, target_time.date())

        # Check in-memory cache first (fast path)
        if cache_key in self._cached_cycles_for_target_time:
            cached_cycles = self._cached_cycles_for_target_time[cache_key]
            _LOGGER.debug(
                "Returning %d in-memory cached cycles for device=%s, date=%s",
                len(cached_cycles),
                device_id,
                target_time.date(),
            )
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager.get_cycles_for_target_time")
            return cached_cycles

        # Calculate window based on retention
        start_time = target_time - timedelta(days=self._device_config.lhs_retention_days)
        end_time = target_time

        # Not in memory cache, get from storage/extraction
        cycles = await self.get_cycles_for_window(device_id, start_time, end_time)

        # Cache in memory for subsequent calls
        self._cached_cycles_for_target_time[cache_key] = cycles
        _LOGGER.debug(
            "Loaded and cached %d cycles in memory for device=%s, date=%s",
            len(cycles),
            device_id,
            target_time.date(),
        )

        # Evict old entries if cache size exceeds limit
        await self._evict_old_memory_cache_entries()

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.get_cycles_for_target_time")
        return cycles

    async def update_cycles_for_window(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract and persist cycles for a specific window.

        Cache Strategy (write operation):
        - **Reads from**: Historical data adapters via _extract_cycles()
        - **Writes to storage cache**: Via cycle_cache.append_cycles() or set_cached_cycles()
        - **Writes to model storage**: Via model_storage.save_heating_cycle() for each cycle
        - **Does NOT write to memory**: Memory cache is populated on-demand by get_cycles_for_target_time()

        Use Case:
        This is the primary write operation for persisting newly extracted cycles.
        Called by:
        - startup(): Initial load
        - on_retention_change(): Reload after retention change
        - on_24h_timer(): Periodic refresh

        Args:
            device_id: Device identifier used for history queries and cache keys.
            start_time: Start of the extraction window.
            end_time: End of the extraction window.

        Returns:
            Newly extracted heating cycles for the window.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.update_cycles_for_window")
        effective_device_id = device_id
        _LOGGER.debug(
            "Updating cycles for device=%s from %s to %s",
            effective_device_id,
            start_time,
            end_time,
        )

        # Extract cycles
        cycles = await self._extract_cycles(effective_device_id, start_time, end_time)

        # Update cache if available
        if self._heating_cycle_storage is not None and cycles:
            try:
                await self._heating_cycle_storage.append_cycles(
                    effective_device_id,
                    cycles,
                    end_time,
                    self._device_config.lhs_retention_days,
                )
                _LOGGER.debug("Updated cache with %d cycles", len(cycles))
            except Exception as exc:
                _LOGGER.error("Error updating cycle cache: %s", exc)

        # Calculate and persist learned dead time from cycles
        _LOGGER.debug(
            "Dead time persistence check: cycles=%d, lhs_storage=%s, auto_learning=%s",
            len(cycles) if cycles else 0,
            "Not None" if self._lhs_storage is not None else "None",
            self._device_config.auto_learning,
        )
        if cycles and self._lhs_storage is not None and self._device_config.auto_learning:
            try:
                from ..domain.services import DeadTimeCalculationService

                dead_time_calculator = DeadTimeCalculationService()
                learned_dead_time = dead_time_calculator.calculate_average_dead_time(cycles)

                _LOGGER.debug(
                    "Calculated learned_dead_time: %s minutes",
                    f"{learned_dead_time:.1f}" if learned_dead_time is not None else "None",
                )

                if learned_dead_time is not None:
                    await self._lhs_storage.set_learned_dead_time(learned_dead_time)
                    _LOGGER.info(
                        "Updated learned dead time from %d cycles: %.1f minutes",
                        len(cycles),
                        learned_dead_time,
                    )
                    if self._dead_time_updated_callback is not None:
                        try:
                            self._dead_time_updated_callback(learned_dead_time)
                        except Exception as exc:
                            _LOGGER.warning("Dead time update callback failed: %s", exc)
            except Exception as exc:
                _LOGGER.warning("Failed to calculate/persist dead time: %s", exc, exc_info=True)
        elif cycles and self._lhs_storage is not None and not self._device_config.auto_learning:
            _LOGGER.debug(
                "Auto-learning disabled; skipping dead time persistence for device=%s",
                effective_device_id,
            )

        # Note: ILhsStorage interface does not include save_heating_cycle()
        # Cycles are extracted from Home Assistant recorder, not persisted via this interface

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.update_cycles_for_window")
        return cycles

    async def cancel(self) -> None:
        """Cancel any scheduled refresh work and release resources.

        Cache Strategy:
        - **Memory cache**: NOT cleared (remains valid until next retention change)
        - **Storage cache**: NOT cleared (persistent data remains)
        - **Timers**: Cancelled to stop periodic refresh

        Use Case:
        Called when the IHP device is being shut down or removed.
        Does NOT clear learned data, only stops active timers.

        Returns:
            None.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.cancel")

        # Cancel all active extraction queues
        queues_to_cancel = self._extraction_queues or (
            [self._extraction_queue] if self._extraction_queue is not None else []
        )
        for queue in queues_to_cancel:
            _LOGGER.info("Cancelling extraction queue during shutdown")
            try:
                await queue.cancel_queue()
            except Exception as exc:
                _LOGGER.warning("Error cancelling extraction queue: %s", exc)

        # Cancel extraction task
        if self._extraction_task is not None:
            _LOGGER.info("Cancelling extraction task")
            self._extraction_task.cancel()
            try:
                await self._extraction_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _LOGGER.warning("Error awaiting cancelled task: %s", exc)

        # Cancel timer if scheduled
        if self._timer_cancel_func is not None:
            try:
                self._timer_cancel_func()
                _LOGGER.debug("Cancelled scheduled timer")
            except Exception as exc:
                _LOGGER.error("Error cancelling timer: %s", exc)
            finally:
                self._timer_cancel_func = None

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.cancel")

    async def _launch_extraction_queue(self) -> None:
        """Launch the asynchronous recording extraction queue for the startup window.

        At startup, only the most recent task_range_days period is extracted to avoid
        overwhelming the Recorder with 10+ devices × 13 tasks = 130 queries at once.
        Full historical coverage is built progressively via trigger_24h_refresh().
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._launch_extraction_queue")

        start_date, end_date = self._calculate_startup_window()
        _LOGGER.info(
            "Startup extraction window: %s to %s (device=%s). "
            "Historical backfill will progress via daily 24h refresh.",
            start_date,
            end_date,
            self._device_config.device_id,
        )
        missing_ranges = await self._find_missing_date_ranges(start_date, end_date)
        await self._launch_extraction_for_ranges(missing_ranges)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._launch_extraction_queue")

    async def _on_cycles_extracted(self, cycles: list[HeatingCycle]) -> None:
        """Callback invoked by extraction queue after each day's extraction completes.

        Performs a synchronous cache update then triggers LHS recalculation cascade.

        Args:
            cycles: List of HeatingCycle objects extracted for one day
        """
        _LOGGER.debug(
            "Entering HeatingCycleLifecycleManager._on_cycles_extracted (cycles=%d)",
            len(cycles),
        )

        if not cycles:
            _LOGGER.debug("No cycles extracted for this day, skipping cache update")
            return

        try:
            # Update heating cycle storage cache (incremental persistence)
            if self._heating_cycle_storage is not None:
                # Use a deterministic search_end_time tied to the extracted data
                search_end_time = max(cycle.end_time for cycle in cycles)
                await self._heating_cycle_storage.append_cycles(
                    self._device_config.device_id,
                    cycles,
                    search_end_time,
                    self._device_config.lhs_retention_days,
                )
                _LOGGER.debug(
                    "Updated heating cycle storage with %d cycles (search_end_time=%s)",
                    len(cycles),
                    search_end_time,
                )

            # Trigger LHS recalculation (cascade update)
            await self._trigger_lhs_cascade(cycles)

            # Persist learned dead time from extracted cycles
            await self._persist_learned_dead_time(cycles)

        except Exception as exc:
            _LOGGER.error("Failed to process extracted cycles: %s", exc)
            # Don't fail - just log and continue

        # Notify that new cycle data is available so sensors can refresh
        if self._on_extraction_complete_callback is not None:
            try:
                self._on_extraction_complete_callback()
            except Exception as exc:
                _LOGGER.warning("Extraction complete callback failed: %s", exc)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._on_cycles_extracted")

    async def _on_period_explored(self, start_date: date, end_date: date) -> None:
        """Callback invoked after each extraction period completes.

        Marks ALL dates in the range as explored, regardless of whether
        cycles were found. This creates a unified, single source of truth:
        explored_dates tracks all days that have been extracted/examined,
        making it the only check needed to determine if a day requires re-extraction.

        Args:
            start_date: First day of the explored period
            end_date: Last day of the explored period
        """
        _LOGGER.debug(
            "Entering HeatingCycleLifecycleManager._on_period_explored (start=%s, end=%s)",
            start_date,
            end_date,
        )

        if self._heating_cycle_storage is None:
            _LOGGER.debug("No heating cycle storage configured, skipping explored date tracking")
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager._on_period_explored")
            return

        # Generate set of ALL dates in the range (explored_dates is the single source of truth)
        explored_dates = set()
        current = start_date
        one_day = timedelta(days=1)
        while current <= end_date:
            explored_dates.add(current)
            current += one_day

        try:
            await self._heating_cycle_storage.append_explored_dates(
                self._device_config.device_id,
                explored_dates,
            )
            _LOGGER.debug(
                "Marked %d dates as explored for device=%s (all dates in period %s-%s)",
                len(explored_dates),
                self._device_config.device_id,
                start_date,
                end_date,
            )
        except Exception as exc:
            _LOGGER.warning("Failed to track explored dates: %s", exc)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._on_period_explored")

    async def trigger_24h_refresh(self) -> None:
        """Trigger a 24-hour data refresh by launching a new extraction queue.

        This is called periodically (or on-demand) to refresh the most recent
        couple days of data without re-extracting all historical data.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.trigger_24h_refresh")

        try:
            # Reschedule next 24h timer for perpetual refresh cycle
            if self._timer_cancel_func is not None:
                try:
                    self._timer_cancel_func()
                except Exception as exc:
                    _LOGGER.warning("Error cancelling previous timer: %s", exc)
                self._timer_cancel_func = None

            if self._timer_scheduler is not None:
                now = dt_util.now() if dt_util is not None else datetime.now()
                next_refresh = now + timedelta(hours=24)
                self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                    next_refresh, self.trigger_24h_refresh
                )
                _LOGGER.debug("Scheduled next 24h refresh timer for %s", next_refresh.isoformat())

            # Step 1: Cancel existing queue if running
            if self._extraction_queue is not None:
                _LOGGER.info("Cancelling previous extraction queue for 24h refresh")
                await self._extraction_queue.cancel_queue()

            # Step 2: Calculate 24h range (yesterday + today only)
            calculator = ExtractionDateRangeCalculator()
            start_date, end_date = calculator.calculate_refresh_range(
                current_time=self._get_current_time_for_extraction(None)
            )

            _LOGGER.info(
                "Starting 24h refresh extraction from %s to %s",
                start_date,
                end_date,
            )

            # Step 3: Create NEW queue instance for refresh
            self._extraction_queue = RecordingExtractionQueue(
                device_id=self._device_config.device_id,
                entity_id=self._device_config.vtherm_entity_id,
                historical_adapters=self._historical_adapters,
                heating_cycle_service=self._heating_cycle_service,
                on_cycles_extracted=self._on_cycles_extracted,
                on_period_explored=self._on_period_explored,
                task_range_days=self._device_config.task_range_days,
                extraction_semaphore=self._extraction_semaphore,
            )

            # Step 4: Populate with 2 days only
            await self._extraction_queue.populate_queue(start_date, end_date)

            # Step 5: Launch new task
            if self._extraction_task is not None:
                self._extraction_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._extraction_task

            self._extraction_task = asyncio.create_task(self._extraction_queue.run_queue())

            _LOGGER.info("24h refresh extraction queue launched")

            # Historical backfill: extend coverage backward by one task_range_days step.
            # This progressively builds the full lhs_retention_days model without
            # overwhelming the Recorder at startup (one extra query per device per day).
            backfill_window = await self._calculate_backfill_window()
            if backfill_window is not None:
                backfill_start, backfill_end = backfill_window
                _LOGGER.info(
                    "Historical backfill step: %s to %s (device=%s)",
                    backfill_start,
                    backfill_end,
                    self._device_config.device_id,
                )
                missing_backfill = await self._find_missing_date_ranges(
                    backfill_start, backfill_end
                )
                if missing_backfill:
                    # Detach recent-refresh references before launching backfill.
                    # _launch_extraction_for_ranges cancels self._extraction_task and
                    # self._extraction_queue first; without this, the just-launched
                    # recent-refresh task (yesterday+today) would be cancelled before
                    # it completes. The detached asyncio.Task continues running until
                    # it finishes, then is garbage-collected.
                    self._extraction_task = None
                    self._extraction_queue = None
                    self._extraction_queues = []
                    await self._launch_extraction_for_ranges(missing_backfill)
                else:
                    _LOGGER.debug(
                        "Backfill window %s-%s already explored for device=%s",
                        backfill_start,
                        backfill_end,
                        self._device_config.device_id,
                    )
            else:
                _LOGGER.debug(
                    "Historical backfill complete for device=%s", self._device_config.device_id
                )

        except Exception as exc:
            _LOGGER.error("Failed to trigger 24h refresh: %s", exc)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.trigger_24h_refresh")

    # ------------------------------------------------------------------
    # Extraction Window Helpers
    # ------------------------------------------------------------------

    def _calculate_startup_window(self) -> tuple[date, date]:
        """Calculate the extraction window for initial startup.

        Returns only the most recent task_range_days period to avoid launching
        N_devices × N_periods queries simultaneously at startup (which overwhelms
        the Recorder and triggers the HA supervisor watchdog with 10+ devices).

        Full historical coverage up to lhs_retention_days is built progressively
        one task_range_days step per 24h refresh cycle via _calculate_backfill_window().

        end_date is always yesterday (never today) to avoid partial cycle extractions.

        Returns:
            Tuple of (start_date, end_date) covering the most recent task_range_days.
        """
        now = self._get_current_time_for_extraction(None)
        end_date = (now - timedelta(days=1)).date()
        start_date = end_date - timedelta(days=self._device_config.task_range_days - 1)
        return start_date, end_date

    async def _calculate_backfill_window(self) -> tuple[date, date] | None:
        """Calculate the next historical period to backfill, or None if complete.

        Looks at the oldest explored date and steps back one task_range_days period.
        Each call to trigger_24h_refresh() advances the backfill frontier one step,
        so the full lhs_retention_days model builds up over ceil(lhs_retention_days /
        task_range_days) daily cycles.

        When the Recorder returns no data for a period (data purged), that period is
        marked as explored by the extraction queue (Fix 1), so the backfill naturally
        stops at the actual Recorder retention boundary without endless retries.

        Returns:
            Tuple of (start_date, end_date) for the next backfill step,
            or None when full coverage is already reached or storage is unavailable.
        """
        if self._heating_cycle_storage is None:
            return None

        oldest = await self._heating_cycle_storage.get_oldest_explored_date(
            self._device_config.device_id
        )
        if oldest is None:
            # Startup window not yet explored — skip backfill this cycle.
            _LOGGER.debug(
                "No explored dates yet for device=%s, skipping backfill",
                self._device_config.device_id,
            )
            return None

        max_start = (
            self._get_current_time_for_extraction(None)
            - timedelta(days=self._device_config.lhs_retention_days)
        ).date()

        if oldest <= max_start + timedelta(days=1):
            _LOGGER.debug(
                "Historical backfill complete for device=%s (oldest=%s >= target=%s)",
                self._device_config.device_id,
                oldest,
                max_start,
            )
            return None

        end_date = oldest - timedelta(days=1)
        start_date = max(
            end_date - timedelta(days=self._device_config.task_range_days - 1),
            max_start,
        )
        return start_date, end_date

    async def _find_missing_date_ranges(
        self,
        window_start: date,
        window_end: date,
    ) -> list[tuple[date, date]]:
        """Find date ranges within the window not yet explored.

        Uses explored_dates as the SINGLE SOURCE OF TRUTH. A day is considered
        "covered" if and only if it exists in explored_dates (regardless of
        whether it contained cycles or was empty).

        Walks every day in [window_start, window_end] and checks whether the
        day has been marked as explored. Consecutive unexplored days are merged
        into contiguous (start, end) ranges to minimize extraction tasks.

        Args:
            window_start: Start of desired coverage window (inclusive).
            window_end: End of desired coverage window (inclusive).

        Returns:
            List of (start, end) date ranges that require extraction.
            Empty list if every day in the window is in explored_dates.
        """
        if self._heating_cycle_storage is None:
            return [(window_start, window_end)]

        cache_data = await self._heating_cycle_storage.get_cache_data(self._device_config.device_id)

        # If no cache data exists, need to extract everything
        if cache_data is None:
            return [(window_start, window_end)]

        # explored_dates is the SINGLE SOURCE OF TRUTH for coverage
        explored_dates = cache_data.explored_dates

        # Walk day-by-day and collect contiguous gaps
        missing_ranges: list[tuple[date, date]] = []
        range_start: date | None = None
        current_day = window_start
        one_day = timedelta(days=1)

        while current_day <= window_end:
            if current_day not in explored_dates:
                # Day has not been explored – start or extend a gap
                if range_start is None:
                    range_start = current_day
            else:
                # Day has been explored – close any open gap
                if range_start is not None:
                    missing_ranges.append((range_start, current_day - one_day))
                    range_start = None
            current_day += one_day

        # Close a gap that extends to window_end
        if range_start is not None:
            missing_ranges.append((range_start, window_end))

        if missing_ranges:
            _LOGGER.debug(
                "Found %d missing range(s) in window [%s, %s]",
                len(missing_ranges),
                window_start,
                window_end,
            )
        else:
            _LOGGER.debug(
                "Cache fully covers window [%s, %s] — no extraction needed",
                window_start,
                window_end,
            )

        return missing_ranges

    async def _launch_extraction_for_ranges(
        self,
        missing_ranges: list[tuple[date, date]],
    ) -> None:
        """Launch async extraction for the given date ranges.

        Cancels any running extraction, then creates one RecordingExtractionQueue
        per missing range and calls populate_queue() once per range. All queues
        are launched concurrently as a single background asyncio gather task.

        Args:
            missing_ranges: List of (start_date, end_date) ranges to extract.
        """
        if not missing_ranges:
            _LOGGER.debug("No missing date ranges – skipping extraction launch")
            return

        # Cancel all existing queues gracefully
        queues_to_cancel = self._extraction_queues or (
            [self._extraction_queue] if self._extraction_queue is not None else []
        )
        for queue in queues_to_cancel:
            _LOGGER.debug("Cancelling previous extraction queue before launching new ones")
            try:
                await queue.cancel_queue()
            except Exception as exc:
                _LOGGER.warning("Error cancelling extraction queue: %s", exc)
        self._extraction_queues = []

        if self._extraction_task is not None:
            self._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._extraction_task
            self._extraction_task = None

        # Create one queue per missing range; call populate_queue() once per range
        run_coroutines: list = []
        for range_start, range_end in missing_ranges:
            queue = RecordingExtractionQueue(
                device_id=self._device_config.device_id,
                entity_id=self._device_config.vtherm_entity_id,
                historical_adapters=self._historical_adapters,
                heating_cycle_service=self._heating_cycle_service,
                on_cycles_extracted=self._on_cycles_extracted,
                on_period_explored=self._on_period_explored,
                task_range_days=self._device_config.task_range_days,
                extraction_semaphore=self._extraction_semaphore,
            )
            task_count = await queue.populate_queue(range_start, range_end)
            self._extraction_queues.append(queue)
            run_coroutines.append(queue.run_queue())
            _LOGGER.info(
                "Queued extraction range %s to %s (%d tasks) for device=%s",
                range_start,
                range_end,
                task_count,
                self._device_config.device_id,
            )

        # Backward-compat alias: _extraction_queue points to the last created queue
        self._extraction_queue = self._extraction_queues[-1] if self._extraction_queues else None

        # Create individual tasks so each run_queue() is directly scheduled on the
        # event loop (ensures _is_running is set after a single asyncio.sleep(0) yield).
        range_tasks = [asyncio.create_task(coro) for coro in run_coroutines]

        # _extraction_task tracks the combined completion of all range tasks.
        async def _wait_all_ranges(tasks: list[asyncio.Task]) -> None:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._extraction_task = asyncio.create_task(_wait_all_ranges(range_tasks))

        # Yield control to allow each run_queue() task to begin processing
        await asyncio.sleep(0)

    async def _persist_learned_dead_time(self, cycles: list[HeatingCycle]) -> None:
        """Calculate and persist learned dead time from cycles.

        This method:
        1. Calculates average dead time from cycles (if auto-learning enabled)
        2. Persists to storage (model_storage)
        3. Fires callback to notify sensors

        Args:
            cycles: Heating cycles used to calculate dead time

        Returns:
            None
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._persist_learned_dead_time")
        _LOGGER.debug(
            "Dead time persistence check: cycles=%d, lhs_storage=%s, auto_learning=%s",
            len(cycles) if cycles else 0,
            "Not None" if self._lhs_storage is not None else "None",
            self._device_config.auto_learning,
        )

        if cycles and self._lhs_storage is not None and self._device_config.auto_learning:
            try:
                from ..domain.services import DeadTimeCalculationService

                dead_time_calculator = DeadTimeCalculationService()
                learned_dead_time = dead_time_calculator.calculate_average_dead_time(cycles)

                _LOGGER.debug(
                    "Calculated learned_dead_time: %s minutes",
                    f"{learned_dead_time:.1f}" if learned_dead_time is not None else "None",
                )

                if learned_dead_time is not None:
                    await self._lhs_storage.set_learned_dead_time(learned_dead_time)
                    _LOGGER.info(
                        "Updated learned dead time from %d cycles: %.1f minutes",
                        len(cycles),
                        learned_dead_time,
                    )
                    if self._dead_time_updated_callback is not None:
                        try:
                            self._dead_time_updated_callback(learned_dead_time)
                        except Exception as exc:
                            _LOGGER.warning("Dead time update callback failed: %s", exc)
            except Exception as exc:
                _LOGGER.warning("Failed to calculate/persist dead time: %s", exc, exc_info=True)
        elif cycles and self._lhs_storage is not None and not self._device_config.auto_learning:
            _LOGGER.debug(
                "Auto-learning disabled; skipping dead time persistence for device=%s",
                self._device_config.device_id,
            )

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._persist_learned_dead_time")

    async def _trigger_lhs_cascade(self, cycles: list[HeatingCycle]) -> None:
        """Trigger cascade update to LHS lifecycle manager with error isolation.

        This method isolates errors between global and contextual LHS updates.
        If global LHS fails, contextual LHS will still be attempted.
        If contextual LHS fails, startup/refresh continues without crashing.

        Error Isolation Strategy:
        - Global LHS failure logs error but does not raise exception
        - Contextual LHS failure logs error but does not raise exception
        - Partial updates are better than complete failure

        Args:
            cycles: Heating cycles to use for LHS recalculation.

        Returns:
            None.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._trigger_lhs_cascade")

        if self._lhs_lifecycle_manager is None:
            _LOGGER.debug("No LHS lifecycle manager configured, skipping cascade")
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager._trigger_lhs_cascade")
            return

        # Attempt global LHS update (isolated error handling)
        try:
            await self._lhs_lifecycle_manager.update_global_lhs_from_cycles(cycles)
            _LOGGER.debug("Successfully updated global LHS with %d cycles", len(cycles))
        except Exception as exc:
            _LOGGER.error(
                "Error updating global LHS (continuing with contextual): %s",
                exc,
                exc_info=True,
            )

        # Attempt contextual LHS update (isolated error handling)
        try:
            await self._lhs_lifecycle_manager.update_contextual_lhs_from_cycles(cycles)
            _LOGGER.debug("Successfully updated contextual LHS with %d cycles", len(cycles))
        except Exception as exc:
            _LOGGER.error(
                "Error updating contextual LHS: %s",
                exc,
                exc_info=True,
            )

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._trigger_lhs_cascade")

    def _get_now_for_scheduling(self, reference_time: datetime) -> datetime:
        """Return a now() timestamp aligned to the reference time's tz awareness."""
        if reference_time.tzinfo is not None and reference_time.tzinfo.utcoffset(reference_time):
            if dt_util is not None:
                return cast(datetime, dt_util.now())
            return datetime.now(tz=reference_time.tzinfo)
        return datetime.now()

    def _get_current_time_for_extraction(self, reference_time: datetime | None) -> datetime:
        """Return a now() timestamp aligned for extraction range calculations."""
        if (
            reference_time is not None
            and reference_time.tzinfo is not None
            and reference_time.tzinfo.utcoffset(reference_time)
        ):
            if dt_util is not None:
                return cast(datetime, dt_util.now())
            return datetime.now(tz=reference_time.tzinfo)
        return cast(datetime, dt_util.now()) if dt_util is not None else datetime.now()

    async def _evict_old_memory_cache_entries(self) -> None:
        """Evict oldest entries from memory cache if limit exceeded.

        Memory Eviction Strategy:
        - Prevents unbounded memory growth in long-running IHP instances
        - Uses LRU (Least Recently Used) based on date
        - Evicts oldest 50% of entries when MAX_MEMORY_CACHE_ENTRIES exceeded
        - Storage cache (Tier 2) preserves data, eviction only affects Tier 1

        Cache Strategy:
        - **Reads from**: _cached_cycles_for_target_time (Tier 1 memory)
        - **Evicts**: Oldest entries by date when cache size > MAX_MEMORY_CACHE_ENTRIES
        - **Does NOT affect**: Tier 2 (IHeatingCycleStorage) or Tier 4 (ILhsStorage)
        - **Lazy reload**: Evicted entries will be reloaded from Tier 2 on next access

        Eviction Algorithm:
        1. Check if cache size exceeds MAX_MEMORY_CACHE_ENTRIES (50)
        2. Sort cache keys by date (oldest first)
        3. Remove oldest 50% of entries (25 entries when at limit)
        4. Log eviction count for monitoring

        Returns:
            None.
        """
        if len(self._cached_cycles_for_target_time) <= MAX_MEMORY_CACHE_ENTRIES:
            return  # No eviction needed

        current_size = len(self._cached_cycles_for_target_time)
        excess = current_size - MAX_MEMORY_CACHE_ENTRIES

        _LOGGER.debug(
            "Memory cache size %d exceeds limit %d, evicting %d entries",
            current_size,
            MAX_MEMORY_CACHE_ENTRIES,
            excess,
        )

        # Sort cache keys by date (oldest first)
        # Key format: (device_id, date)
        sorted_keys = sorted(
            self._cached_cycles_for_target_time.keys(),
            key=lambda k: k[1],  # k[1] is the date
        )

        # Evict oldest entries to bring cache back to limit
        keys_to_remove = sorted_keys[:excess]

        for key in keys_to_remove:
            device_id, date = key
            del self._cached_cycles_for_target_time[key]
            _LOGGER.info("Evicted heating cycle for device %s from %s", device_id, date)

        _LOGGER.debug(
            "Evicted %d old memory cache entries (cache size now %d)",
            len(keys_to_remove),
            len(self._cached_cycles_for_target_time),
        )

    async def _extract_cycles(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract heating cycles from historical data.

        Args:
            device_id: Device identifier
            start_time: Start of extraction window
            end_time: End of extraction window

        Returns:
            List of extracted heating cycles
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._extract_cycles")

        # Diagnostic logs for troubleshooting empty data issue
        _LOGGER.debug(
            "Extracting cycles for device_id=%s, time window: %s to %s",
            device_id,
            start_time.isoformat(),
            end_time.isoformat(),
        )
        _LOGGER.debug("Number of historical adapters available: %d", len(self._historical_adapters))
        if not self._historical_adapters:
            _LOGGER.warning(
                "No historical adapters configured for device_id=%s. "
                "This will result in empty historical data. "
                "Check factory initialization.",
                device_id,
            )

        # Load historical data from all adapters
        combined_data: HistoricalDataSet = HistoricalDataSet(data={})

        for adapter in self._historical_adapters:
            try:
                # Call the interface method to fetch historical data for each data key
                # Use the configured VTherm entity ID from device_config, not the device_id
                vtherm_entity_id = self._device_config.vtherm_entity_id
                _LOGGER.debug(
                    "Fetching historical data from adapter for entity_id=%s",
                    vtherm_entity_id,
                )
                for data_key in HistoricalDataKey:
                    adapter_data = await adapter.fetch_historical_data(
                        entity_id=vtherm_entity_id,
                        data_key=data_key,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    # Merge adapter data into combined_data
                    if adapter_data is not None and adapter_data.data:
                        # Only extend if this data_key exists in the adapter response
                        if data_key in adapter_data.data:
                            if data_key not in combined_data.data:
                                combined_data.data[data_key] = []
                            combined_data.data[data_key].extend(adapter_data.data[data_key])
                        else:
                            _LOGGER.debug(
                                "Data key %s not found in adapter response for entity %s",
                                data_key.value,
                                device_id,
                            )
            except Exception as exc:
                _LOGGER.error("Error loading data from adapter: %s", exc)
                raise

        # Create historical dataset
        historical_data_set = HistoricalDataSet(data=combined_data.data)

        # Extract cycles using domain service
        cycles = await self._heating_cycle_service.extract_heating_cycles(
            device_id=device_id,
            history_data_set=historical_data_set,
            start_time=start_time,
            end_time=end_time,
        )

        _LOGGER.debug("Extracted %d cycles from historical data", len(cycles))
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._extract_cycles")
        return cycles

    # ------------------------------------------------------------------
    # Async Incremental Extraction Integration Methods
    # ------------------------------------------------------------------
    # These methods orchestrate the incremental daily extraction using
    # RecordingExtractionQueue to load data asynchronously without freezing
    # Home Assistant.

    async def _trigger_incremental_extraction(
        self,
        device_id: str,
        extraction_start_date: date,
        extraction_end_date: date,
    ) -> None:
        """Trigger asynchronous incremental extraction for a date range.

        Creates a RecordingExtractionQueue instance, populates it with daily
        tasks, and runs extraction asynchronously in the background. As each
        day completes, extracted cycles are fed into the cycle storage cache
        and cascade updates to LhsLifecycleManager.

        This method does NOT block and returns immediately. The extraction
        continues asynchronously in the background, keeping Home Assistant
        responsive during the large historical data load.

        Args:
            device_id: Device identifier for extraction
            extraction_start_date: Start date for extraction (inclusive)
            extraction_end_date: End date for extraction (inclusive)

        Returns:
            None (extraction runs asynchronously in background)
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._trigger_incremental_extraction")
        await self._launch_extraction_for_ranges([(extraction_start_date, extraction_end_date)])
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._trigger_incremental_extraction")

    async def _on_incremental_extraction_day_complete(
        self,
        cycles: list[HeatingCycle],
    ) -> None:
        """Callback invoked after each day's extraction completes.

        This callback is called by RecordingExtractionQueue after successfully
        extracting cycles for a single day. Responsibility:
        1. Save extracted cycles to persistent storage
        2. Cascade update to LhsLifecycleManager with new cycles
        3. Update in-memory cache to avoid immediate re-query

        This enables progressive model availability: after 1-2 days of extraction,
        the ML model becomes usable even if the full ~90 days haven't loaded yet.

        Args:
            cycles: List of extracted HeatingCycle objects from one day

        Returns:
            None
        """
        _LOGGER.debug(
            "Entering HeatingCycleLifecycleManager._on_incremental_extraction_day_complete"
        )
        await self._on_cycles_extracted(cycles)
        _LOGGER.debug(
            "Exiting HeatingCycleLifecycleManager._on_incremental_extraction_day_complete"
        )

    async def can_cancel_extraction(self) -> bool:
        """Check if there is an ongoing extraction that can be cancelled.

        Returns True if an extraction queue is currently running and can be
        stopped via cancel_extraction().

        Returns:
            True if extraction is running, False otherwise
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.can_cancel_extraction")
        if self._extraction_task is None:
            _LOGGER.debug("No extraction running (task is None)")
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager.can_cancel_extraction")
            return False
        if self._extraction_task.done():
            _LOGGER.debug("Extraction task is already done")
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager.can_cancel_extraction")
            return False
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.can_cancel_extraction")
        return True

    async def cancel_extraction(self) -> None:
        """Cancel an ongoing incremental extraction gracefully.

        If an extraction is running via RecordingExtractionQueue, this method
        requests cancellation. The queue will finish the current day's extraction
        and then stop without processing remaining days.

        Has no effect if no extraction is currently running.

        Returns:
            None
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.cancel_extraction")
        queues_to_cancel = self._extraction_queues or (
            [self._extraction_queue] if self._extraction_queue is not None else []
        )
        if queues_to_cancel:
            _LOGGER.info(
                "Cancelling ongoing incremental extraction (%d queue(s))", len(queues_to_cancel)
            )
            for queue in queues_to_cancel:
                try:
                    await queue.cancel_queue()
                except Exception as exc:
                    _LOGGER.warning("Error requesting extraction queue cancellation: %s", exc)
        else:
            _LOGGER.debug("No extraction queue to cancel")
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.cancel_extraction")

    async def on_demand_extraction(
        self,
        device_id: str,
        start_date: date,
        end_date: date,
    ) -> list[HeatingCycle]:
        """Trigger on-demand extraction for a custom date range.

        This method allows explicit extraction of a specific date range outside
        the normal startup/refresh cycle. Useful for:
        - Manual cache refresh
        - Recovery from extraction failures
        - User-triggered data loads

        The extraction runs asynchronously and returns a list of cycles extracted
        during this request.

        Args:
            device_id: Device identifier
            start_date: Start date for extraction (inclusive)
            end_date: End date for extraction (inclusive)

        Returns:
            List of all HeatingCycle objects extracted for the date range
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.on_demand_extraction")

        # Validate device_id matches this manager's device
        if device_id != self._device_config.device_id:
            raise ValueError(
                f"on_demand_extraction called with device_id='{device_id}' but this manager "
                f"is scoped to device_id='{self._device_config.device_id}'"
            )

        _LOGGER.info(
            "On-demand extraction requested: device=%s from %s to %s",
            device_id,
            start_date,
            end_date,
        )

        collected_cycles: list[HeatingCycle] = []

        async def _collect(cycles: list[HeatingCycle]) -> None:
            """Collect cycles from each day's extraction and update caches."""
            collected_cycles.extend(cycles)
            # Also persist and cascade LHS as with background extraction
            await self._on_cycles_extracted(cycles)

        async def _track_explored(start_date: date, end_date: date) -> None:
            """Track explored dates (with or without cycles)."""
            await self._on_period_explored(start_date, end_date)

        # Create a dedicated queue (does not replace the background queue)
        demand_queue = RecordingExtractionQueue(
            device_id=device_id,
            entity_id=self._device_config.vtherm_entity_id,
            historical_adapters=self._historical_adapters,
            heating_cycle_service=self._heating_cycle_service,
            on_cycles_extracted=_collect,
            on_period_explored=_track_explored,
            task_range_days=self._device_config.task_range_days,
            extraction_semaphore=self._extraction_semaphore,
        )

        try:
            await demand_queue.populate_queue(start_date, end_date)
            # Run synchronously (await): caller expects cycles in the return value
            await demand_queue.run_queue()
        except Exception as exc:
            _LOGGER.error("On-demand extraction failed: %s", exc)
            raise

        # Check for per-day failures that were swallowed inside run_queue()
        extracted, total, _ = await demand_queue.get_progress()
        failed = total - extracted
        if failed > 0:
            raise RuntimeError(
                f"On-demand extraction had {failed}/{total} day(s) fail "
                f"for device={device_id} ({start_date} to {end_date})"
            )

        _LOGGER.info(
            "On-demand extraction complete: extracted %d cycles for device=%s",
            len(collected_cycles),
            device_id,
        )
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.on_demand_extraction")
        return collected_cycles
