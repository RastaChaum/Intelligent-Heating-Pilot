"""Lifecycle manager for learned heating slope (LHS) caching and refresh."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from ..domain.value_objects.heating import HeatingCycle

if TYPE_CHECKING:
    from ..domain.interfaces import ILhsStorage, ITimerScheduler
    from ..domain.services.contextual_lhs_calculator_service import ContextualLHSCalculatorService
    from ..domain.services.global_lhs_calculator_service import GlobalLHSCalculatorService

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.util import dt as dt_util
except ImportError:
    dt_util = None  # For testing without HA


class LhsLifecycleManager:
    """Manage global and contextual LHS lifecycle, caching, and refresh.

    This manager is a singleton per IHP device (identified by device_id).
    It orchestrates:
    1. In-memory cache management (_cached_global_lhs, _cached_contextual_lhs)
    2. Persistent storage via ILhsStorage
    3. Periodic refresh scheduling (24h timer)
    4. Cascade updates triggered by HeatingCycleLifecycleManager

    Architecture:
    - **In-memory cache**: Fast lookups for global and contextual LHS values
    - **Model storage (ILhsStorage)**: Persistent storage for LHS values with timestamps
    - **Triggered by**: HeatingCycleLifecycleManager when cycles change

    Lazy Loading Strategy:
    ========================
    This class implements LAZY LOADING for contextual LHS to optimize startup performance:

    **Startup Phase:**
    - Global LHS: Loaded eagerly (single read from storage)
    - Contextual LHS: Loaded ONLY for current hour (datetime.now().hour)
    - Other 23 hours: NOT loaded at startup (deferred to on-demand)

    **On-Demand Loading:**
    - get_contextual_lhs(): Loads requested hour from storage (if not in memory)
    - ensure_contextual_lhs_populated(): Same lazy-load behavior with optional force_recalculate
    - Per-hour memory caching: Each hour cached independently after first load

    **Bulk Update Methods (intentionally load all 24 hours):**
    - on_retention_change(): Recalculates and caches all 24 hours when retention changes
    - on_24h_timer(): Recalculates and caches all 24 hours on periodic refresh
    - update_contextual_lhs_from_cycles(): Persists all 24 hours when called

    Cache Hierarchy (fastest to slowest):
    1. Memory cache (_cached_contextual_lhs[hour]): O(1) lookup
    2. Storage cache (ILhsStorage.get_cached_contextual_lhs): Single disk read
    3. Computation cache (calculate_contextual_lhs_for_hour): On-demand calculation

    Lifecycle Events:
    - startup(): Load global LHS + current hour contextual (lazy loading)
    - on_retention_change(cycles): Recalculate ALL 24 hours with new retention window
    - on_24h_timer(cycles): Recalculate ALL 24 hours on timer event
    - update_global_lhs_from_cycles(cycles): Persist global LHS from cycles
    - update_contextual_lhs_from_cycles(cycles): Persist ALL 24 contextual hours from cycles
    - cancel(): Cleanup timers and release resources (keep cached data)

    Cascade Pattern:
    HeatingCycleLifecycleManager calls update_*_lhs_from_cycles() when:
    - startup(): Initial cycles extracted
    - on_retention_change(): Cycles re-extracted with new retention
    - on_24h_timer(): Cycles refreshed with latest data
    """

    def __init__(
        self,
        model_storage: ILhsStorage,
        global_lhs_calculator: GlobalLHSCalculatorService,
        contextual_lhs_calculator: ContextualLHSCalculatorService,
        timer_scheduler: ITimerScheduler | None = None,
    ) -> None:
        """Initialize the lifecycle manager.

        Note: This should be instantiated via LhsLifecycleManagerFactory
        to ensure singleton behavior per device_id.

        Args:
            model_storage: Persistent storage adapter for cached LHS values.
            global_lhs_calculator: Domain service for computing global LHS from cycles.
            contextual_lhs_calculator: Domain service for computing contextual LHS by hour from cycles.
            timer_scheduler: Optional scheduler for periodic 24h refresh tasks.
        """
        self._model_storage = model_storage
        self._global_lhs_calculator = global_lhs_calculator
        self._contextual_lhs_calculator = contextual_lhs_calculator
        self._timer_scheduler = timer_scheduler

        # In-memory caches for fast repeated lookups (avoids disk I/O)
        # These are loaded from storage on startup and invalidated on updates
        self._cached_global_lhs: float | None = None  # Global LHS value
        self._cached_contextual_lhs: dict[int, float] = {}  # hour (0-23) -> LHS value
        self._timer_cancel_func: Callable[[], None] | None = None

    async def startup(self) -> None:
        """Initialize LHS caches and schedule periodic refresh.

        Lifecycle Event Flow:
        1. Load cached global LHS from storage → memory cache
        2. Load cached contextual LHS for CURRENT HOUR ONLY (lazy loading)
        3. Schedule 24h timer for automatic refresh (if scheduler provided)

        Lazy Loading Strategy:
        This method implements lazy loading to optimize startup performance:
        - **Current hour**: Loaded eagerly during startup (most frequently used)
        - **Other 23 hours**: Loaded on-demand via get_contextual_lhs() or ensure_contextual_lhs_populated()
        - **Memory cache**: Per-hour caching in _cached_contextual_lhs (fast lookups)
        - **Storage cache**: Persistent on-disk cache (fallback if not in memory)
        - **Computation cache**: Computed on-demand when no cached value exists

        Cache Strategy:
        - **Reads from storage**: model_storage.get_cached_global_lhs()
        - **Reads from storage**: model_storage.get_cached_contextual_lhs() for CURRENT HOUR ONLY
        - **Writes to memory**: Populates _cached_global_lhs and _cached_contextual_lhs[current_hour]
        - **Does NOT write to storage**: Only loads existing cached values
        - **Does NOT compute**: Uses cached values or returns defaults via get_* methods

        Note:
        - Initial LHS values are computed and stored by HeatingCycleLifecycleManager during its startup
        - Bulk updates (on_retention_change(), on_24h_timer()) intentionally load all 24 hours
        - On-demand loads (get_contextual_lhs(), ensure_contextual_lhs_populated()) load per-hour

        Returns:
            None.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.startup")

        try:
            # Load cached global LHS
            cached_global_lhs = await self._model_storage.get_cached_global_lhs()
            if cached_global_lhs is not None:
                # Extract value from LHSCacheEntry
                lhs_value = cached_global_lhs.value
                self._cached_global_lhs = lhs_value
                _LOGGER.debug("Loaded cached global LHS: %.2f °C/h", lhs_value)

            # Lazy Loading: Load contextual LHS for current hour ONLY
            # Other hours will be loaded on-demand via get_contextual_lhs() or ensure_contextual_lhs_populated()
            current_hour = datetime.now().hour if dt_util is None else dt_util.now().hour
            _LOGGER.debug(
                "Loading contextual LHS for current hour: %d (lazy loading enabled)", current_hour
            )

            cached_contextual = await self._model_storage.get_cached_contextual_lhs(current_hour)
            if cached_contextual is not None:
                # Extract value from LHSCacheEntry
                lhs_value = cached_contextual.value
                self._cached_contextual_lhs[current_hour] = lhs_value
                _LOGGER.debug(
                    "Loaded cached contextual LHS for current hour %d: %.2f °C/h",
                    current_hour,
                    lhs_value,
                )
            else:
                _LOGGER.debug(
                    "No cached contextual LHS for current hour %d; will load on-demand",
                    current_hour,
                )

            _LOGGER.info(
                "LHS startup complete: loaded global LHS and current hour contextual LHS (lazy loading enabled)"
            )
        except Exception as exc:
            _LOGGER.error("Error during startup: %s", exc)
            # Don't re-raise - continue with defaults

        # Schedule 24h timer for automatic refresh
        if self._timer_scheduler is not None:
            if dt_util is not None:
                next_refresh = dt_util.now() + timedelta(hours=24)
            else:
                next_refresh = datetime.now() + timedelta(hours=24)

            # Timer callback: no-op placeholder (cycles provided by HeatingCycleLifecycleManager)
            async def noop_callback() -> None:
                """Placeholder timer callback - actual update comes from HCLM."""
                pass

            self._timer_cancel_func = self._timer_scheduler.schedule_timer(
                next_refresh, noop_callback
            )
            _LOGGER.debug("Scheduled 24h LHS refresh timer for %s", next_refresh.isoformat())

        _LOGGER.debug("Exiting LhsLifecycleManager.startup")

    async def on_retention_change(self, cycles: list[HeatingCycle]) -> None:
        """Handle retention configuration changes.

        Lifecycle Event Flow (triggered by HeatingCycleLifecycleManager):
        1. HeatingCycleLifecycleManager re-extracts cycles for new retention window
        2. HeatingCycleLifecycleManager calls this method with the new cycles
        3. Invalidate in-memory caches FIRST (prevents use of stale data)
        4. Recalculate global LHS from provided cycles
        5. Recalculate contextual LHS (by hour) from provided cycles
        6. Persist new LHS values to storage

        Cache Strategy:
        - **Invalidates memory FIRST**: Clears _cached_global_lhs and _cached_contextual_lhs
        - **Receives cycles from**: HeatingCycleLifecycleManager.on_retention_change()
        - **Computes**: global_lhs_calculator.calculate_global_lhs(cycles)
        - **Computes**: contextual_lhs_calculator.calculate_contextual_lhs(cycles)
        - **Writes to storage**: model_storage.set_cached_global_lhs()
        - **Writes to storage**: model_storage.set_cached_contextual_lhs(hour, value)

        Args:
            cycles: Heating cycles extracted for the new retention window.

        Returns:
            None.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.on_retention_change")
        _LOGGER.debug("Recalculating LHS from %d cycles after retention change", len(cycles))

        # Step 1: Invalidate in-memory caches FIRST (before any computation)
        self._cached_global_lhs = None
        self._cached_contextual_lhs = {}
        _LOGGER.debug("Invalidated in-memory caches before recalculation")

        # Step 2: Recalculate global LHS from provided cycles
        global_lhs = self._global_lhs_calculator.calculate_global_lhs(cycles)
        updated_at = dt_util.now() if dt_util is not None else datetime.now()
        await self._model_storage.set_cached_global_lhs(global_lhs, updated_at)
        _LOGGER.info("Recalculated global LHS: %.2f °C/h", global_lhs)

        # Step 3: Recalculate contextual LHS from provided cycles
        contextual_lhs_by_hour = self._contextual_lhs_calculator.calculate_all_contextual_lhs(
            cycles
        )
        for hour, lhs_value in contextual_lhs_by_hour.items():
            if lhs_value is not None:
                await self._model_storage.set_cached_contextual_lhs(hour, lhs_value, updated_at)
        _LOGGER.debug("Recalculated contextual LHS for %d hours", len(contextual_lhs_by_hour))

        _LOGGER.debug("Exiting LhsLifecycleManager.on_retention_change")

    async def on_24h_timer(self, cycles: list[HeatingCycle]) -> None:
        """Handle periodic 24h refresh execution.

        Lifecycle Event Flow (triggered by HeatingCycleLifecycleManager):
        1. HeatingCycleLifecycleManager extracts fresh cycles for retention window
        2. HeatingCycleLifecycleManager calls this method with the fresh cycles
        3. Recalculate global LHS from provided cycles
        4. Recalculate contextual LHS (by hour) from provided cycles
        5. Persist new LHS values to storage
        6. Invalidate in-memory caches (will reload from storage on next access)

        Cache Strategy:
        - **Receives cycles from**: HeatingCycleLifecycleManager.on_24h_timer()
        - **Computes**: global_lhs_calculator.calculate_global_lhs(cycles)
        - **Computes**: contextual_lhs_calculator.calculate_contextual_lhs(cycles)
        - **Writes to storage**: model_storage.set_cached_global_lhs()
        - **Writes to storage**: model_storage.set_cached_contextual_lhs(hour, value)
        - **Invalidates memory**: Sets _cached_global_lhs = None, _cached_contextual_lhs = {}

        Args:
            cycles: Heating cycles extracted for the current retention window.

        Returns:
            None.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.on_24h_timer")
        _LOGGER.info("24h LHS refresh timer triggered")

        # Recalculate global LHS from provided cycles
        global_lhs = self._global_lhs_calculator.calculate_global_lhs(cycles)
        updated_at = dt_util.now() if dt_util is not None else datetime.now()
        await self._model_storage.set_cached_global_lhs(global_lhs, updated_at)
        # Invalidate cache to ensure fresh load
        self._cached_global_lhs = None
        _LOGGER.info("Refreshed global LHS: %.2f °C/h", global_lhs)

        # Recalculate contextual LHS from provided cycles
        contextual_lhs_by_hour = self._contextual_lhs_calculator.calculate_all_contextual_lhs(
            cycles
        )
        for hour, lhs_value in contextual_lhs_by_hour.items():
            if lhs_value is not None:
                await self._model_storage.set_cached_contextual_lhs(hour, lhs_value, updated_at)
        # Invalidate cache to ensure fresh load
        self._cached_contextual_lhs = {}

        _LOGGER.debug("Exiting LhsLifecycleManager.on_24h_timer")

    async def get_global_lhs(self) -> float:
        """Return the global learned heating slope (LHS).

        Cache Strategy (read-only, optimized with memory cache):
        - **Reads from memory first**: Checks _cached_global_lhs
        - **On memory cache hit**: Returns immediately (fast path)
        - **On memory cache miss**: Loads from model_storage.get_cached_global_lhs()
        - **Writes to memory**: Caches loaded value in _cached_global_lhs
        - **Validation**: Returns default if cached value is invalid (<=0 or None)
        - **Does NOT write to storage**: Read-only operation

        Use Case:
        Called frequently during anticipation calculations to get the baseline heating rate.
        Memory cache ensures fast lookups without repeated disk I/O.

        Returns:
            The cached or default global LHS in C/hour.
        """
        from ..domain.constants import DEFAULT_LEARNED_SLOPE

        _LOGGER.debug("Entering LhsLifecycleManager.get_global_lhs")

        # Check in-memory cache first (fast path)
        if self._cached_global_lhs is not None:
            _LOGGER.debug(
                "Returning in-memory cached global LHS: %.2f °C/h", self._cached_global_lhs
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.get_global_lhs")
            return self._cached_global_lhs

        # Not in memory cache, load from storage
        cached_entry = await self._model_storage.get_cached_global_lhs()

        # Validate cached value is positive
        if cached_entry is not None:
            cached_lhs = cached_entry.value
            if cached_lhs > 0:
                # Cache in memory for subsequent calls
                self._cached_global_lhs = cached_lhs
                _LOGGER.debug("Loaded from storage and cached global LHS: %.2f °C/h", cached_lhs)
                _LOGGER.debug("Exiting LhsLifecycleManager.get_global_lhs")
                return cached_lhs

        # Return default if cache invalid or missing
        _LOGGER.debug(
            "No valid cached global LHS, returning default: %.2f °C/h", DEFAULT_LEARNED_SLOPE
        )
        _LOGGER.debug("Exiting LhsLifecycleManager.get_global_lhs")
        return DEFAULT_LEARNED_SLOPE

    async def cancel(self) -> None:
        """Cancel any scheduled refresh work and release resources.

        Cache Strategy:
        - **Memory cache**: NOT cleared (remains valid until next update)
        - **Storage cache**: NOT cleared (persistent data remains)
        - **Timers**: Cancelled to stop periodic refresh

        Use Case:
        Called when the IHP device is being shut down or removed.
        Does NOT clear learned data, only stops active timers.

        Returns:
            None.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.cancel")

        # Cancel timer if scheduled
        if self._timer_cancel_func is not None:
            try:
                self._timer_cancel_func()
                _LOGGER.debug("Cancelled scheduled timer")
            except Exception as exc:
                _LOGGER.error("Error cancelling timer: %s", exc)
            finally:
                self._timer_cancel_func = None

        _LOGGER.debug("Exiting LhsLifecycleManager.cancel")

    async def get_contextual_lhs(
        self,
        target_time: datetime,
        cycles: list[HeatingCycle],
    ) -> float:
        """Return contextual LHS for a target time.

        Cache Strategy (read-only, optimized with memory cache per hour):
        - **Reads from memory first**: Checks _cached_contextual_lhs[target_hour]
        - **On memory cache hit**: Returns immediately (fast path)
        - **On memory cache miss**: Loads from model_storage.get_cached_contextual_lhs(hour)
        - **If no storage cache**: Computes from provided cycles
        - **Writes to memory**: Caches loaded/computed value in _cached_contextual_lhs[hour]
        - **Falls back to global LHS**: If no contextual data exists for the hour
        - **Does NOT write to storage**: Read-only operation (use update_contextual_lhs_from_cycles)

        Use Case:
        Called during anticipation calculations to get hour-specific heating rates.
        Memory cache per hour ensures fast lookups without repeated disk I/O.

        Args:
            target_time: Target datetime used to select the contextual hour (0-23).
            cycles: Heating cycles used to compute contextual LHS when not cached.

        Returns:
            Contextual LHS for the target hour in C/hour, or global LHS fallback.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.get_contextual_lhs")

        target_hour = target_time.hour
        _LOGGER.debug("Getting contextual LHS for hour %d", target_hour)

        # Check in-memory cache first (fast path)
        if target_hour in self._cached_contextual_lhs:
            cached_value = self._cached_contextual_lhs[target_hour]
            _LOGGER.debug(
                "Returning in-memory cached contextual LHS for hour %d: %.2f °C/h",
                target_hour,
                cached_value,
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.get_contextual_lhs")
            return cached_value

        # Not in memory cache, try to get from storage
        cached_entry = await self._model_storage.get_cached_contextual_lhs(target_hour)

        if cached_entry is not None:
            cached_contextual = cached_entry.value
            # Cache in memory for subsequent calls
            self._cached_contextual_lhs[target_hour] = cached_contextual
            _LOGGER.debug(
                "Loaded from storage and cached contextual LHS for hour %d: %.2f °C/h",
                target_hour,
                cached_contextual,
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.get_contextual_lhs")
            return cached_contextual

        # No cache, compute contextual LHS for THIS HOUR ONLY (not all 24)
        _LOGGER.debug("No cached contextual LHS for hour %d, computing from cycles", target_hour)
        computed_lhs = self._contextual_lhs_calculator.calculate_contextual_lhs_for_hour(
            cycles, target_hour
        )

        # If contextual LHS is None, fallback to global LHS
        if computed_lhs is None:
            _LOGGER.debug(
                "No contextual LHS computed for hour %d, falling back to global LHS",
                target_hour,
            )
            return await self.get_global_lhs()

        # Cache computed value in memory
        self._cached_contextual_lhs[target_hour] = computed_lhs
        _LOGGER.debug(
            "Computed and cached contextual LHS for hour %d: %.2f °C/h",
            target_hour,
            computed_lhs,
        )
        _LOGGER.debug("Exiting LhsLifecycleManager.get_contextual_lhs")
        return computed_lhs

    async def update_global_lhs_from_cycles(self, cycles: list[HeatingCycle]) -> float:
        """Recalculate and persist global LHS from cycles.

        Lifecycle Event (triggered by HeatingCycleLifecycleManager):
        This is called when:
        - HeatingCycleLifecycleManager.startup(): Initial cycles extracted
        - HeatingCycleLifecycleManager.on_retention_change(): Cycles re-extracted
        - HeatingCycleLifecycleManager.on_24h_timer(): Cycles refreshed

        Cache Strategy (write operation):
        - **Receives cycles from**: HeatingCycleLifecycleManager
        - **Computes**: global_lhs_calculator.calculate_global_lhs(cycles)
        - **Writes to storage**: model_storage.set_cached_global_lhs(lhs, timestamp)
        - **Invalidates memory**: Sets _cached_global_lhs = None
        - **Next read**: get_global_lhs() will reload from storage into memory

        Args:
            cycles: Heating cycles used to compute the global LHS.

        Returns:
            The computed and persisted global LHS in C/hour.
        """
        from ..domain.constants import DEFAULT_LEARNED_SLOPE

        _LOGGER.debug("Entering LhsLifecycleManager.update_global_lhs_from_cycles")
        _LOGGER.debug("Updating global LHS from %d cycles", len(cycles))

        try:
            global_lhs = self._global_lhs_calculator.calculate_global_lhs(cycles)
            updated_at = dt_util.now() if dt_util is not None else datetime.now()
            await self._model_storage.set_cached_global_lhs(global_lhs, updated_at)

            # Update in-memory cache with new value for fast subsequent access
            self._cached_global_lhs = global_lhs
            _LOGGER.debug("Updated global LHS in-memory cache: %.2f °C/h", global_lhs)

            _LOGGER.info("Updated global LHS: %.2f °C/h", global_lhs)
            _LOGGER.debug("Exiting LhsLifecycleManager.update_global_lhs_from_cycles")
            return global_lhs
        except Exception as exc:
            _LOGGER.error("Error calculating global LHS: %s", exc)
            _LOGGER.debug("Exiting LhsLifecycleManager.update_global_lhs_from_cycles")
            return DEFAULT_LEARNED_SLOPE

    async def update_contextual_lhs_from_cycles(
        self,
        cycles: list[HeatingCycle],
    ) -> dict[int, float | None]:
        """Recalculate and persist contextual LHS for all hours.

        Lifecycle Event (triggered by HeatingCycleLifecycleManager):
        This is called when:
        - HeatingCycleLifecycleManager.startup(): Initial cycles extracted
        - HeatingCycleLifecycleManager.on_retention_change(): Cycles re-extracted
        - HeatingCycleLifecycleManager.on_24h_timer(): Cycles refreshed

        Cache Strategy (write operation):
        - **Receives cycles from**: HeatingCycleLifecycleManager
        - **Computes**: contextual_lhs_calculator.calculate_contextual_lhs(cycles)
        - **Writes to storage**: model_storage.set_cached_contextual_lhs(hour, lhs, timestamp) for each hour
        - **Invalidates memory**: Sets _cached_contextual_lhs = {}
        - **Next read**: get_contextual_lhs() will reload from storage into memory per hour

        Args:
            cycles: Heating cycles used to compute contextual LHS by hour.

        Returns:
            Mapping of hour (0-23) to LHS in C/hour, or None when no data exists.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.update_contextual_lhs_from_cycles")
        _LOGGER.debug("Updating contextual LHS from %d cycles", len(cycles))

        contextual_lhs_by_hour = self._contextual_lhs_calculator.calculate_all_contextual_lhs(
            cycles
        )

        # Persist non-None values with timestamp
        updated_at = dt_util.now() if dt_util is not None else datetime.now()

        persisted_count = 0
        for hour, lhs_value in contextual_lhs_by_hour.items():
            if lhs_value is not None:
                await self._model_storage.set_cached_contextual_lhs(hour, lhs_value, updated_at)
                persisted_count += 1

        # Update in-memory cache with new values for fast subsequent access
        # Only cache non-None values
        self._cached_contextual_lhs = {
            hour: lhs for hour, lhs in contextual_lhs_by_hour.items() if lhs is not None
        }
        _LOGGER.debug(
            "Updated contextual LHS in-memory cache for %d hours", len(self._cached_contextual_lhs)
        )

        _LOGGER.info("Updated contextual LHS for %d hours", persisted_count)
        _LOGGER.debug("Exiting LhsLifecycleManager.update_contextual_lhs_from_cycles")

        return contextual_lhs_by_hour

    async def ensure_contextual_lhs_populated(
        self,
        target_hour: int,
        cycles: list[HeatingCycle],
        force_recalculate: bool = False,
    ) -> float:
        """Ensure contextual LHS is populated for a specific hour.

        Lazy Population Strategy:
        This method is called when anticipation calculation needs LHS for a specific hour
        but it's not in the cache (memory or storage).

        Cache Strategy (write operation with lazy loading):
        - **If force_recalculate=True**: Skip cache checks, recompute immediately
        - **Reads from memory first**: Checks _cached_contextual_lhs[target_hour]
        - **On memory cache hit**: Returns immediately (fast path)
        - **Reads from storage**: Tries model_storage.get_cached_contextual_lhs(hour)
        - **On storage cache hit**: Loads into memory, returns
        - **On cache miss**: Computes from provided cycles
        - **Writes to storage**: model_storage.set_cached_contextual_lhs(hour, value, timestamp)
        - **Writes to memory**: Updates _cached_contextual_lhs[hour]
        - **Fallback**: Returns global LHS if no contextual data exists

        Use Case:
        Called during anticipation calculations when:
        - Cache is cold (first run after startup)
        - Hour-specific LHS was never calculated
        - Explicit refresh requested (force_recalculate=True)

        Args:
            target_hour: Hour to ensure LHS is populated for (0-23).
            cycles: Heating cycles to use if computation is needed.
            force_recalculate: If True, bypass cache and recompute from cycles.

        Returns:
            Contextual LHS for the target hour in C/hour, or global LHS fallback.
        """
        _LOGGER.debug("Entering LhsLifecycleManager.ensure_contextual_lhs_populated")
        _LOGGER.debug(
            "Ensuring contextual LHS populated for hour %d (force_recalculate=%s)",
            target_hour,
            force_recalculate,
        )

        # If force_recalculate, skip cache checks and recompute THIS HOUR ONLY
        if force_recalculate:
            _LOGGER.debug("Force recalculate enabled, bypassing cache for hour %d", target_hour)
            computed_lhs = self._contextual_lhs_calculator.calculate_contextual_lhs_for_hour(
                cycles, target_hour
            )

            # Persist if value exists
            if computed_lhs is not None:
                updated_at = dt_util.now() if dt_util is not None else datetime.now()
                await self._model_storage.set_cached_contextual_lhs(
                    target_hour, computed_lhs, updated_at
                )
                # Update memory cache
                self._cached_contextual_lhs[target_hour] = computed_lhs
                _LOGGER.debug(
                    "Forced recalculation: contextual LHS for hour %d: %.2f °C/h",
                    target_hour,
                    computed_lhs,
                )
                _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
                return computed_lhs

            # No contextual data, fallback to global LHS
            _LOGGER.debug("No contextual LHS for hour %d, falling back to global", target_hour)
            global_lhs = await self.get_global_lhs()
            _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
            return global_lhs

        # Check memory cache first (fast path)
        if target_hour in self._cached_contextual_lhs:
            cached_value = self._cached_contextual_lhs[target_hour]
            _LOGGER.debug(
                "Contextual LHS already in memory cache for hour %d: %.2f °C/h",
                target_hour,
                cached_value,
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
            return cached_value

        # Check storage cache
        cached_entry = await self._model_storage.get_cached_contextual_lhs(target_hour)

        if cached_entry is not None:
            cached_contextual = cached_entry.value
            # Load into memory cache for subsequent calls
            self._cached_contextual_lhs[target_hour] = cached_contextual
            _LOGGER.debug(
                "Loaded contextual LHS from storage for hour %d: %.2f °C/h",
                target_hour,
                cached_contextual,
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
            return cached_contextual

        # No cache, compute contextual LHS for THIS HOUR ONLY (not all 24)
        _LOGGER.debug("No cached contextual LHS for hour %d, computing from cycles", target_hour)
        computed_lhs = self._contextual_lhs_calculator.calculate_contextual_lhs_for_hour(
            cycles, target_hour
        )

        # If contextual LHS exists, persist and cache
        if computed_lhs is not None:
            updated_at = dt_util.now() if dt_util is not None else datetime.now()
            await self._model_storage.set_cached_contextual_lhs(
                target_hour, computed_lhs, updated_at
            )
            # Cache in memory for subsequent calls
            self._cached_contextual_lhs[target_hour] = computed_lhs
            _LOGGER.debug(
                "Computed and cached contextual LHS for hour %d: %.2f °C/h",
                target_hour,
                computed_lhs,
            )
            _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
            return computed_lhs

        # No contextual data, fallback to global LHS
        _LOGGER.debug("No contextual LHS for hour %d, falling back to global LHS", target_hour)
        global_lhs = await self.get_global_lhs()
        _LOGGER.debug("Exiting LhsLifecycleManager.ensure_contextual_lhs_populated")
        return global_lhs
