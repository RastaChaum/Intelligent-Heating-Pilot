"""Lifecycle manager for heating cycle extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ..domain.interfaces.device_config_reader_interface import DeviceConfig
from ..domain.interfaces.heating_cycle_service_interface import IHeatingCycleService
from ..domain.value_objects.heating import HeatingCycle
from ..domain.value_objects.historical_data import HistoricalDataKey, HistoricalDataSet

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

        # In-memory cache for fast repeated lookups
        # Key: (device_id, target_date) → list[HeatingCycle]
        # This avoids re-extracting cycles from storage/history for the same device/date
        self._cached_cycles_for_target_time: dict[tuple[str, date], list[HeatingCycle]] = {}
        self._timer_cancel_func: Callable[[], None] | None = None

    async def startup(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Run startup extraction and schedule periodic refresh.

        Lifecycle Event Flow:
        1. Extract cycles from historical data for [start_time, end_time]
        2. Save cycles to persistent storage (IHeatingCycleStorage + ILhsStorage)
        3. Load cycles into in-memory cache for fast access
        4. Cascade to LhsLifecycleManager to update LHS values
        5. Schedule 24h timer for automatic refresh

        Cache Strategy:
        - **Reads from**: Historical data adapters via _extract_cycles()
        - **Writes to**: Persistent storage via update_cycles_for_window()
        - **Loads into memory**: Via get_cycles_for_target_time() on subsequent calls
        - **Cascades to**: LHS manager to update global/contextual LHS

        Args:
            device_id: Device identifier used for history queries and cache keys.
            start_time: Start of the extraction window (typically now - retention_days).
            end_time: End of the extraction window (typically now).

        Returns:
            Extracted heating cycles for the initial window.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.startup")
        _LOGGER.debug(
            "Startup extraction for device=%s from %s to %s", device_id, start_time, end_time
        )

        try:
            # Step 1: Extract and persist cycles (writes to storage)
            cycles = await self.update_cycles_for_window(device_id, start_time, end_time)

            # Step 2: Cascade to LHS lifecycle manager to update LHS caches
            await self._trigger_lhs_cascade(cycles)

            # Step 3: Schedule 24h timer if scheduler provided
            if self._timer_scheduler is not None:
                if dt_util is not None:
                    next_refresh = dt_util.now() + timedelta(hours=24)
                else:
                    next_refresh = datetime.now() + timedelta(hours=24)

                self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                    next_refresh, self.on_24h_timer
                )
                _LOGGER.debug("Scheduled 24h cycle refresh timer for %s", next_refresh.isoformat())

            _LOGGER.info("Startup complete: extracted %d cycles and updated LHS", len(cycles))
            _LOGGER.debug("Exiting HeatingCycleLifecycleManager.startup")
            return cycles
        except Exception as exc:
            _LOGGER.error("Error during startup: %s", exc)
            raise

    async def on_retention_change(self, new_retention_days: int) -> None:
        """Handle retention configuration changes.

        Lifecycle Event Flow:
        1. Update device_config with new retention period
        2. Clear in-memory cache (invalidated by retention change)
        3. Clear persistent storage cache (IHeatingCycleStorage)
        4. Re-extract cycles for new retention window
        5. Save new cycles to persistent storage
        6. Cascade to LhsLifecycleManager to recalculate LHS with new window

        Cache Strategy:
        - **Invalidates memory**: Clears _cached_cycles_for_target_time
        - **Invalidates storage**: Calls cycle_cache.clear_cache()
        - **Reads from**: Historical data adapters for new window
        - **Writes to**: Persistent storage via update_cycles_for_window()
        - **Cascades to**: LHS manager with new cycles

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

        # Step 4: Re-extract cycles for new retention window
        end_time = dt_util.now() if dt_util is not None else datetime.now()
        start_time = end_time - timedelta(days=new_retention_days)

        cycles = await self.update_cycles_for_window(
            self._device_config.device_id,
            start_time,
            end_time,
        )
        _LOGGER.debug("Re-extracted %d cycles for new retention window", len(cycles))

        # Step 5: Cascade to LHS lifecycle manager to recalculate with new window
        await self._trigger_lhs_cascade(cycles)

        _LOGGER.debug("Exiting HeatingCycleLifecycleManager.on_retention_change")

    async def on_24h_timer(self) -> None:
        """Handle periodic 24h refresh execution.

        Lifecycle Event Flow:
        1. Calculate new extraction window (now - retention_days to now)
        2. Extract cycles from historical data
        3. Save cycles to persistent storage (replacing old data outside retention)
        4. Prune cycles older than retention period from storage
        5. Cascade to LhsLifecycleManager to recalculate LHS
        6. Update in-memory cache will happen on next get_cycles_for_target_time() call

        Cache Strategy:
        - **Reads from**: Historical data adapters for retention window
        - **Writes to**: Persistent storage via update_cycles_for_window()
        - **Prunes from storage**: Old cycles via cycle_cache.prune_old_cycles()
        - **Memory cache**: Not updated here, will reload on next query
        - **Cascades to**: LHS manager to update global/contextual LHS

        Returns:
            None.
        """
        _LOGGER.debug("Entering HeatingCycleLifecycleManager.on_24h_timer")
        _LOGGER.info("24h cycle refresh timer triggered")

        try:
            # Step 1: Calculate extraction window for retention period
            end_time = dt_util.now() if dt_util is not None else datetime.now()
            start_time = end_time - timedelta(days=self._device_config.lhs_retention_days)

            # Step 2: Extract and persist cycles (writes to storage)
            cycles = await self.update_cycles_for_window(
                self._device_config.device_id,
                start_time,
                end_time,
            )
            _LOGGER.info("24h refresh complete: extracted %d cycles", len(cycles))

            # Step 3: Prune old cycles from storage cache
            if self._heating_cycle_storage is not None:
                await self._heating_cycle_storage.prune_old_cycles(
                    self._device_config.device_id, end_time
                )
                _LOGGER.debug("Pruned old cycles from storage cache")

            # Step 4: Cascade to LHS lifecycle manager to recalculate with fresh data
            await self._trigger_lhs_cascade(cycles)

            # Step 5: Reschedule timer for next 24h refresh
            if self._timer_scheduler is not None:
                if dt_util is not None:
                    next_refresh = dt_util.now() + timedelta(hours=24)
                else:
                    next_refresh = datetime.now() + timedelta(hours=24)

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
        _LOGGER.debug(
            "Updating cycles for device=%s from %s to %s", device_id, start_time, end_time
        )

        # Extract cycles
        cycles = await self._extract_cycles(device_id, start_time, end_time)

        # Update cache if available
        if self._heating_cycle_storage is not None and cycles:
            try:
                await self._heating_cycle_storage.append_cycles(
                    device_id,
                    cycles,
                    end_time,
                    self._device_config.lhs_retention_days,
                )
                _LOGGER.debug("Updated cache with %d cycles", len(cycles))
            except Exception as exc:
                _LOGGER.error("Error updating cycle cache: %s", exc)

        # Calculate and persist learned dead time from cycles
        if cycles and self._lhs_storage is not None:
            try:
                from ..domain.services import DeadTimeCalculationService

                dead_time_calculator = DeadTimeCalculationService()
                learned_dead_time = dead_time_calculator.calculate_average_dead_time(cycles)

                if learned_dead_time is not None:
                    await self._lhs_storage.set_learned_dead_time(learned_dead_time)
                    _LOGGER.info(
                        "Updated learned dead time from %d cycles: %.1f minutes",
                        len(cycles),
                        learned_dead_time,
                    )
            except Exception as exc:
                _LOGGER.warning("Failed to calculate/persist dead time: %s", exc)

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
