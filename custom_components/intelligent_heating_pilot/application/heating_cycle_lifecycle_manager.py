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
    - startup(): Initial load from storage → memory, schedule 24h timer, cascade LHS update
    - on_retention_change(): Clear caches, reload with new retention, cascade LHS update
    - on_24h_timer(): Refresh cycles for retention window, cascade LHS update
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
        """
        self._device_config = device_config
        self._heating_cycle_service = heating_cycle_service
        self._historical_adapters = historical_adapters
        self._heating_cycle_storage = heating_cycle_storage
        self._timer_scheduler = timer_scheduler
        self._lhs_storage = lhs_storage
        self._lhs_lifecycle_manager = lhs_lifecycle_manager
        self._dead_time_updated_callback = dead_time_updated_callback

        # In-memory cache for fast repeated lookups
        # Key: (device_id, target_date) → list[HeatingCycle]
        # This avoids re-extracting cycles from storage/history for the same device/date
        self._cached_cycles_for_target_time: dict[tuple[str, date], list[HeatingCycle]] = {}
        self._timer_cancel_func: Callable[[], None] | None = None

        # Extraction queue for asynchronous incremental Recorder loading
        self._extraction_queue: RecordingExtractionQueue | None = None
        self._extraction_task: asyncio.Task | None = None

    async def startup(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Run startup and schedule periodic refresh.

        Lifecycle Event Flow:
        1. Schedule 24h timer at now() + 24H (regardless of end_time)
        2. Calculate extraction window: start = now - retention_days, end = yesterday
        3. Check cache for missing date ranges
        4. Launch async extraction only for missing ranges

        Cycles are delivered asynchronously via the _on_cycles_extracted() callback.

        Args:
            device_id: Device identifier (kept for backward compatibility).
            start_time: Ignored; window is computed from now() and retention.
            end_time: Ignored; window end is always yesterday to avoid partial cycles.

        Returns:
            Empty list; cycles are delivered asynchronously via callback.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.startup")
        _LOGGER.debug("Startup for device=%s", device_id)

        try:
            # Step 1: Schedule 24h timer at now() + 24H regardless of end_time
            if self._timer_scheduler is not None:
                now = self._get_current_time_for_extraction(None)
                next_refresh = now + timedelta(hours=24)
                self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                    next_refresh, self.on_24h_timer
                )
                _LOGGER.debug("Scheduled 24h cycle refresh timer for %s", next_refresh.isoformat())

            # Step 2: Calculate extraction window (end = yesterday, not today)
            start_date, end_date = self._calculate_extraction_window()
            _LOGGER.debug("Extraction window: %s to %s", start_date, end_date)

            # Step 3: Find missing date ranges vs current cache
            missing_ranges = await self._find_missing_date_ranges(start_date, end_date)

            # Step 4: Launch async extraction for missing ranges only
            if missing_ranges:
                await self._launch_extraction_for_ranges(missing_ranges)
                _LOGGER.info(
                    "Startup: launched async extraction for %d missing range(s)", len(missing_ranges)
                )
            else:
                _LOGGER.info("Startup: cache is up to date, no extraction needed")

            _LOGGER.info("Startup complete: extraction running asynchronously")
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager.startup")
            return []
        except Exception as exc:
            _LOGGER.error("Error during startup: %s", exc)
            raise

    async def on_retention_change(self, new_retention_days: int) -> None:
        """Handle retention configuration changes.

        Lifecycle Event Flow:
        1. Update device_config with new retention period
        2. Clear in-memory cache (invalidated by retention change)
        3. Clear persistent storage cache (IHeatingCycleStorage)
        4. Calculate new extraction window and launch async extraction for the full window

        Cycles are delivered asynchronously via the _on_cycles_extracted() callback.

        Args:
            new_retention_days: Updated retention window in days.

        Returns:
            None.
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

        # Step 3: Clear persistent storage cache
        if self._heating_cycle_storage is not None and hasattr(
            self._heating_cycle_storage, "clear_cache"
        ):
            try:
                await self._heating_cycle_storage.clear_cache(self._device_config.device_id)
                _LOGGER.debug("Cleared storage cycle cache due to retention change")
            except (AttributeError, TypeError):
                pass

        # Step 4: Calculate new window and find missing ranges (full window since cache cleared)
        start_date, end_date = self._calculate_extraction_window()
        missing_ranges = await self._find_missing_date_ranges(start_date, end_date)

        # Step 5: Launch async extraction for missing ranges
        await self._launch_extraction_for_ranges(missing_ranges)
        _LOGGER.info("Retention change: launched async extraction for new window")

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.on_retention_change")

    async def on_24h_timer(self) -> None:
        """Handle periodic 24h refresh execution.

        Lifecycle Event Flow:
        1. Calculate extraction window (now - retention_days to yesterday)
        2. Find missing date ranges vs current cache
        3. Launch async extraction for missing ranges
        4. Prune old cycles from storage
        5. Reschedule timer at now() + 24H

        Cycles are delivered asynchronously via the _on_cycles_extracted() callback.

        Returns:
            None.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.on_24h_timer")
        _LOGGER.info("24h cycle refresh timer triggered")

        try:
            # Step 1: Calculate extraction window (end = yesterday, not today)
            start_date, end_date = self._calculate_extraction_window()

            # Step 2: Find missing date ranges vs cache
            missing_ranges = await self._find_missing_date_ranges(start_date, end_date)

            # Step 3: Launch async extraction for missing ranges
            await self._launch_extraction_for_ranges(missing_ranges)
            _LOGGER.info("24h refresh: launched async extraction for missing ranges")

            # Step 4: Prune old cycles from storage cache
            if self._heating_cycle_storage is not None:
                now = self._get_current_time_for_extraction(None)
                await self._heating_cycle_storage.prune_old_cycles(
                    self._device_config.device_id, now
                )
                _LOGGER.debug("Pruned old cycles from storage cache")

            # Step 5: Reschedule timer at now() + 24H (not based on end_time)
            if self._timer_scheduler is not None:
                now = self._get_current_time_for_extraction(None)
                next_refresh = now + timedelta(hours=24)
                self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                    next_refresh, self.on_24h_timer
                )
                _LOGGER.debug(
                    "Rescheduled 24h cycle refresh timer for %s", next_refresh.isoformat()
                )

        except Exception as exc:
            _LOGGER.error("Error during 24h cycle refresh: %s", exc)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.on_24h_timer")

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

        # No cache, extract cycles
        cycles = await self._extract_cycles(device_id, start_time, end_time)
        _LOGGER.debug("Extracted %d cycles without cache", len(cycles))
        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.get_cycles_for_window")
        return cycles

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

        # Cancel extraction queue if running
        if self._extraction_queue is not None:
            _LOGGER.info("Cancelling extraction queue during shutdown")
            try:
                await self._extraction_queue.cancel_queue()
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
        """Launch the asynchronous recording extraction queue.

        Delegates to _launch_extraction_for_ranges after computing the extraction
        window and finding missing date ranges. Kept for backward compatibility.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager._launch_extraction_queue")

        start_date, end_date = self._calculate_extraction_window()
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
            # Feed cycles into lhs storage cache
            if self._lhs_storage is not None:
                cache_heating_cycle = getattr(self._lhs_storage, "cache_heating_cycle", None)
                if callable(cache_heating_cycle):
                    for cycle in cycles:
                        await cache_heating_cycle(cycle)

                    _LOGGER.info(
                        "Cached %d heating cycles from extraction queue",
                        len(cycles),
                    )

            # Update heating cycle storage cache (synchronous cache update)
            if self._heating_cycle_storage is not None:
                now = self._get_current_time_for_extraction(None)
                await self._heating_cycle_storage.append_cycles(
                    self._device_config.device_id,
                    cycles,
                    now,
                    self._device_config.lhs_retention_days,
                )
                _LOGGER.debug("Updated heating cycle storage with %d cycles", len(cycles))

            # Trigger LHS recalculation (cascade update)
            await self._trigger_lhs_cascade(cycles)

        except Exception as exc:
            _LOGGER.error("Failed to process extracted cycles: %s", exc)
            # Don't fail - just log and continue

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager._on_cycles_extracted")

    async def trigger_24h_refresh(self) -> None:
        """Trigger a 24-hour data refresh by launching a new extraction queue.

        This is called periodically (or on-demand) to refresh the most recent
        couple days of data without re-extracting all historical data.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.trigger_24h_refresh")

        try:
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
                climate_entity_id=self._device_config.vtherm_entity_id,
                historical_adapters=self._historical_adapters,
                heating_cycle_service=self._heating_cycle_service,
                on_cycles_extracted=self._on_cycles_extracted,
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

        except Exception as exc:
            _LOGGER.error("Failed to trigger 24h refresh: %s", exc)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.trigger_24h_refresh")

    # ------------------------------------------------------------------
    # Extraction Window Helpers
    # ------------------------------------------------------------------

    def _calculate_extraction_window(self) -> tuple[date, date]:
        """Calculate the extraction window for heating cycles.

        end_date is always yesterday (never today) to avoid partial cycle
        extractions for the current day.

        Returns:
            Tuple of (start_date, end_date) for extraction.
        """
        now = self._get_current_time_for_extraction(None)
        end_date = (now - timedelta(days=1)).date()
        start_date = (now - timedelta(days=self._device_config.lhs_retention_days)).date()
        return start_date, end_date

    async def _find_missing_date_ranges(
        self,
        window_start: date,
        window_end: date,
    ) -> list[tuple[date, date]]:
        """Find date ranges within the window not yet covered by the cache.

        Compares the desired window against cycles already stored in cache and
        returns only the sub-ranges that need extraction.

        Args:
            window_start: Start of desired coverage window.
            window_end: End of desired coverage window.

        Returns:
            List of (start, end) date ranges that require extraction.
            Empty list if cache fully covers the window.
        """
        if self._heating_cycle_storage is None:
            return [(window_start, window_end)]

        cache_data = await self._heating_cycle_storage.get_cache_data(
            self._device_config.device_id
        )

        if cache_data is None or not cache_data.cycles:
            return [(window_start, window_end)]

        # Find oldest and newest cycle dates in cache
        oldest_date = min(cycle.start_time.date() for cycle in cache_data.cycles)
        newest_date = max(cycle.start_time.date() for cycle in cache_data.cycles)

        # Cache fully covers the window – nothing to extract
        if oldest_date <= window_start and newest_date >= window_end:
            _LOGGER.debug(
                "Cache fully covers window [%s, %s] (cache: [%s, %s])",
                window_start,
                window_end,
                oldest_date,
                newest_date,
            )
            return []

        missing_ranges: list[tuple[date, date]] = []

        # Gap before the oldest cached cycle
        if oldest_date > window_start:
            missing_ranges.append((window_start, oldest_date - timedelta(days=1)))

        # Gap after the newest cached cycle
        if newest_date < window_end:
            missing_ranges.append((newest_date + timedelta(days=1), window_end))

        return missing_ranges

    async def _launch_extraction_for_ranges(
        self,
        missing_ranges: list[tuple[date, date]],
    ) -> None:
        """Launch async extraction for the given date ranges.

        Cancels any running extraction, merges all ranges into one contiguous
        span, creates a new RecordingExtractionQueue and starts it as a
        background asyncio task.

        Args:
            missing_ranges: List of (start_date, end_date) ranges to extract.
        """
        if not missing_ranges:
            _LOGGER.debug("No missing date ranges – skipping extraction launch")
            return

        # Cancel existing queue gracefully
        if self._extraction_queue is not None:
            _LOGGER.debug("Cancelling previous extraction queue before launching new one")
            try:
                await self._extraction_queue.cancel_queue()
            except Exception as exc:
                _LOGGER.warning("Error cancelling extraction queue: %s", exc)

        if self._extraction_task is not None:
            self._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._extraction_task
            self._extraction_task = None

        # Merge all missing ranges into one contiguous range
        start_date = min(r[0] for r in missing_ranges)
        end_date = max(r[1] for r in missing_ranges)

        _LOGGER.info(
            "Launching async extraction from %s to %s for device=%s",
            start_date,
            end_date,
            self._device_config.device_id,
        )

        # Create new extraction queue
        self._extraction_queue = RecordingExtractionQueue(
            device_id=self._device_config.device_id,
            climate_entity_id=self._device_config.vtherm_entity_id,
            historical_adapters=self._historical_adapters,
            heating_cycle_service=self._heating_cycle_service,
            on_cycles_extracted=self._on_cycles_extracted,
        )

        # Populate queue with daily tasks
        task_count = await self._extraction_queue.populate_queue(start_date, end_date)
        _LOGGER.info(
            "Extraction queue populated with %d daily tasks for device=%s",
            task_count,
            self._device_config.device_id,
        )

        # Launch queue as background asyncio task (non-blocking)
        self._extraction_task = asyncio.create_task(self._extraction_queue.run_queue())

        # Yield control to allow queue to begin processing
        await asyncio.sleep(0)

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
        raise NotImplementedError("_trigger_incremental_extraction is not implemented yet")

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
        raise NotImplementedError("_on_incremental_extraction_day_complete is not implemented yet")

    async def can_cancel_extraction(self) -> bool:
        """Check if there is an ongoing extraction that can be cancelled.

        Returns True if an extraction queue is currently running and can be
        stopped via cancel_extraction().

        Returns:
            True if extraction is running, False otherwise
        """
        raise NotImplementedError("can_cancel_extraction is not implemented yet")

    async def cancel_extraction(self) -> None:
        """Cancel an ongoing incremental extraction gracefully.

        If an extraction is running via RecordingExtractionQueue, this method
        requests cancellation. The queue will finish the current day's extraction
        and then stop without processing remaining days.

        Has no effect if no extraction is currently running.

        Returns:
            None
        """
        raise NotImplementedError("cancel_extraction is not implemented yet")

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
        raise NotImplementedError("on_demand_extraction is not implemented yet")
