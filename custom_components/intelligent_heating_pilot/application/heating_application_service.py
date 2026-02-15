"""Application service - orchestrates domain and infrastructure.

This service coordinates between the domain layer (HeatingPilot, PredictionService)
and infrastructure adapters, implementing use cases.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.util import dt as dt_util

from ..const import DEFAULT_DATA_RETENTION_DAYS, DEFAULT_DECISION_MODE
from ..domain.entities import HeatingPilot
from ..domain.services import (
    ContextualLHSCalculatorService,
    DeadTimeCalculationService,
    GlobalLHSCalculatorService,
    HeatingCycleService,
    PredictionService,
)
from ..domain.value_objects import (
    HeatingCycle,
    HistoricalDataKey,
    HistoricalDataSet,
)
from ..infrastructure.decision_strategy_factory import DecisionStrategyFactory

if TYPE_CHECKING:
    from ..domain.interfaces import (
        IClimateDataReader,
        IContextReader,
        IEnvironmentReader,
        ITimerScheduler,
    )
    from ..infrastructure.adapters import (
        HAClimateCommander,
        HAHeatingCycleStorage,
        HALhsStorage,
        HASchedulerCommander,
        HASchedulerReader,
    )
    from .heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager
    from .lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)
LHS_CACHE_TTL_HOURS = 24


class HeatingApplicationService:
    """Application service orchestrating heating control use cases.

    This service is the main entry point for heating logic, coordinating:
    - Domain aggregates (HeatingPilot)
    - Domain services (PredictionService)
    - Infrastructure adapters (HA*)

    NO Home Assistant dependencies - only uses adapter interfaces.
    """

    def __init__(
        self,
        scheduler_reader: HASchedulerReader,
        model_storage: HALhsStorage,
        scheduler_commander: HASchedulerCommander,
        climate_commander: HAClimateCommander,
        environment_reader: IEnvironmentReader,
        climate_data_reader: IClimateDataReader,
        environment_context_reader: IContextReader,
        timer_scheduler: ITimerScheduler,
        cycle_cache: HAHeatingCycleStorage | None = None,
        lhs_window_hours: float = 6.0,
        history_lookback_days: int | None = None,
        decision_mode: str = DEFAULT_DECISION_MODE,
        temp_delta_threshold: float | None = None,
        cycle_split_duration_minutes: int = 0,
        min_cycle_duration_minutes: int | None = None,
        max_cycle_duration_minutes: int | None = None,
        dead_time_minutes: float = 0.0,
        auto_learning: bool = True,
        heating_cycle_lifecycle_manager: HeatingCycleLifecycleManager | None = None,
        lhs_lifecycle_manager: LhsLifecycleManager | None = None,
        on_lhs_changed: Callable[[], Any] | None = None,
    ) -> None:
        """Initialize the application service.

        Args:
            scheduler_reader: Reads scheduled timeslots
            model_storage: Persists learned slopes
            scheduler_commander: Triggers scheduler actions
            climate_commander: Controls climate entity
            environment_reader: Reads environmental conditions
            climate_data_reader: Unified reader for VTherm metadata, slope and heating state
            environment_context_reader: Provides adapter context and sensor metadata
            timer_scheduler: Schedules timer callbacks for anticipation
            cycle_cache: Optional cache for heating cycles (enables incremental updates)
            lhs_window_hours: Time window in hours for contextual LHS (default: 6)
            history_lookback_days: Number of days of HA history to query
                to extract heating cycles (default: DEFAULT_DATA_RETENTION_DAYS)
            decision_mode: Decision mode ('simple' or 'ml')
            temp_delta_threshold: Temperature threshold for cycle detection (°C)
            cycle_split_duration_minutes: Duration for splitting long cycles (minutes, 0=disabled)
            min_cycle_duration_minutes: Minimum cycle duration (minutes)
            max_cycle_duration_minutes: Maximum cycle duration (minutes)
            dead_time_minutes: Dead time in minutes (initial heating delay)
            auto_learning: If True, learn parameters from heating cycles
            heating_cycle_lifecycle_manager: Manager for cycle lifecycle orchestration
            lhs_lifecycle_manager: Manager for LHS lifecycle orchestration
            on_lhs_changed: Callback invoked when global LHS is recalculated
        """
        self._scheduler_reader = scheduler_reader
        self._model_storage = model_storage
        self._scheduler_commander = scheduler_commander
        self._climate_commander = climate_commander
        self._environment_reader = environment_reader
        self._climate_data_reader = climate_data_reader
        self._environment_context_reader = environment_context_reader
        self._timer_scheduler = timer_scheduler
        self._cycle_cache = cycle_cache
        self._prediction_service = PredictionService()
        self._global_lhs_calculator = GlobalLHSCalculatorService()
        self._contextual_lhs_calculator = ContextualLHSCalculatorService()
        self._dead_time_calculator = DeadTimeCalculationService()

        # Create HeatingCycleService with configured parameters
        from ..const import (
            DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
            DEFAULT_MAX_CYCLE_DURATION_MINUTES,
            DEFAULT_MIN_CYCLE_DURATION_MINUTES,
            DEFAULT_TEMP_DELTA_THRESHOLD,
        )

        self._heating_cycle_service = HeatingCycleService(
            temp_delta_threshold=temp_delta_threshold or DEFAULT_TEMP_DELTA_THRESHOLD,
            cycle_split_duration_minutes=cycle_split_duration_minutes
            or DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
            min_cycle_duration_minutes=min_cycle_duration_minutes
            or DEFAULT_MIN_CYCLE_DURATION_MINUTES,
            max_cycle_duration_minutes=max_cycle_duration_minutes
            or DEFAULT_MAX_CYCLE_DURATION_MINUTES,
        )

        self._lhs_window_hours = lhs_window_hours
        self._history_lookback_days = (
            int(history_lookback_days)
            if history_lookback_days is not None
            else int(DEFAULT_DATA_RETENTION_DAYS)
        )
        self._dead_time_minutes = dead_time_minutes
        self._auto_learning = auto_learning
        self._heating_cycle_lifecycle_manager = heating_cycle_lifecycle_manager
        self._lhs_lifecycle_manager = lhs_lifecycle_manager
        self._on_lhs_changed = on_lhs_changed

        # Create decision strategy based on mode
        decision_strategy = DecisionStrategyFactory.create_strategy(
            mode=decision_mode,
            scheduler_reader=scheduler_reader,
            model_storage=model_storage,
        )

        # Create HeatingPilot with strategy
        self._heating_pilot = HeatingPilot(
            decision_strategy=decision_strategy,
            scheduler_commander=scheduler_commander,
        )

        _LOGGER.info(f"HeatingApplicationService initialized with decision mode: {decision_mode}")

        # Runtime state for anticipation scheduling
        self._last_scheduled_time: datetime | None = None
        self._last_scheduled_lhs: float | None = None
        self._is_preheating_active: bool = False
        self._preheating_target_time: datetime | None = None
        self._active_scheduler_entity: str | None = None  # Track which scheduler is being used

        # Cancel function returned by timer scheduler for active timer
        self._anticipation_timer_cancel: Callable[[], None] | None = None

        # Lock to protect timer state transitions from race conditions
        self._timer_lock = asyncio.Lock()

    async def _clear_anticipation_state(self) -> None:
        """Clear all anticipation tracking state."""
        await self._cancel_anticipation_timer()
        self._is_preheating_active = False
        self._preheating_target_time = None
        self._last_scheduled_time = None
        self._last_scheduled_lhs = None
        self._active_scheduler_entity = None
        _LOGGER.debug("Anticipation state cleared")

    async def _cancel_anticipation_timer(self) -> None:
        """Cancel any active anticipation timer.

        Protected by lock to prevent race conditions during cancellation.
        """
        async with self._timer_lock:
            self._cancel_anticipation_timer_internal()

    def _cancel_anticipation_timer_internal(self) -> None:
        """Cancel timer without lock protection (for internal use within lock)."""
        if self._anticipation_timer_cancel is not None:
            _LOGGER.debug("Cancelling active anticipation timer")
            self._anticipation_timer_cancel()
            self._anticipation_timer_cancel = None

    async def _schedule_anticipation_timer(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
    ) -> None:
        """Schedule a timer to trigger anticipation at the specified time.

        Protected by lock to prevent race conditions during timer scheduling.

        Args:
            anticipated_start: When to trigger the anticipation
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
        """
        _LOGGER.debug(
            "Entering _schedule_anticipation_timer: anticipated_start=%s, scheduler=%s",
            anticipated_start.isoformat(),
            scheduler_entity_id,
        )

        # Create callback for timer (outside lock - will execute later when timer fires)
        async def _trigger_callback() -> None:
            """Callback to trigger anticipation when timer fires."""
            _LOGGER.info(
                "Anticipation timer fired at %s for target %s (%.1f°C)",
                dt_util.now().isoformat(),
                target_time.isoformat(),
                target_temp,
            )

            # Use lock to protect timer state transitions
            async with self._timer_lock:
                # Clear the timer reference since it has fired
                self._anticipation_timer_cancel = None

                # Trigger the action
                await self._trigger_anticipation_action(
                    target_time,
                    target_temp,
                    scheduler_entity_id,
                )

        async with self._timer_lock:
            # Cancel any existing timer first
            self._cancel_anticipation_timer_internal()

            # Track which scheduler we're anticipating for
            self._active_scheduler_entity = scheduler_entity_id
            # Schedule the timer using the interface
            self._anticipation_timer_cancel = self._timer_scheduler.schedule_timer(
                anticipated_start,
                _trigger_callback,
            )

            now = dt_util.now()
            wait_minutes = (anticipated_start - now).total_seconds() / 60.0
            _LOGGER.info(
                "Anticipation timer scheduled: will trigger at %s (in %.1f minutes)",
                anticipated_start.isoformat(),
                wait_minutes,
            )

        _LOGGER.debug("Exiting _schedule_anticipation_timer")

    async def _trigger_anticipation_action(
        self,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        on_lhs_changed: Callable[[], Any] | None = None,
    ) -> None:
        """Trigger the anticipation action (run scheduler action).

        Args:
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            on_lhs_changed: Optional callback when LHS changes
        """
        _LOGGER.debug(
            "Entering _trigger_anticipation_action: target_time=%s, temp=%.1f°C, scheduler=%s",
            target_time.isoformat(),
            target_temp,
            scheduler_entity_id,
        )
        _LOGGER.info(
            "Triggering anticipation action for target %s (%.1f°C)",
            target_time.isoformat(),
            target_temp,
        )

        # Check if scheduler is still enabled
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning(
                "Scheduler %s is disabled. Cannot trigger anticipation action.",
                scheduler_entity_id,
            )
            await self._clear_anticipation_state()
            return

        # Use scheduler's run_action to trigger the action
        await self._scheduler_commander.run_action(target_time, scheduler_entity_id)

        # Mark pre-heating as active
        self._is_preheating_active = True
        self._preheating_target_time = target_time
        self._active_scheduler_entity = scheduler_entity_id

        _LOGGER.debug("Exiting _trigger_anticipation_action")

    # NOTE: process_slope_update() removed - we now extract slopes directly from
    # Home Assistant recorder via HeatingCycleService, so no disk-based persistence needed

    async def _get_cycles_and_calculate_parameters(
        self, target_time: datetime
    ) -> tuple[list[HeatingCycle], float, float]:
        """Get heating cycles and calculate both LHS and dead_time from them.

        This consolidates cycle extraction to avoid duplicate calls to cache/recorder.

        Args:
            target_time: Target schedule time

        Returns:
            Tuple of (heating_cycles, contextual_lhs, effective_dead_time)
        """
        target_hour = target_time.hour
        _LOGGER.debug(
            "Extracting cycles and calculating LHS + dead_time for hour %02d%s",
            target_hour,
            " (with cache)" if self._cycle_cache else "",
        )

        if not self._heating_cycle_lifecycle_manager or not self._lhs_lifecycle_manager:
            raise NotImplementedError

        # Get device ID
        vtherm_id = self._climate_data_reader.get_vtherm_entity_id()

        heating_cycles = await self._heating_cycle_lifecycle_manager.get_cycles_for_target_time(
            device_id=vtherm_id,
            target_time=target_time,
        )

        contextual_lhs = await self._lhs_lifecycle_manager.get_contextual_lhs(
            target_time=target_time,
            cycles=heating_cycles,
        )

        # Calculate effective dead_time
        if self._auto_learning and heating_cycles:
            # Auto-learning enabled: calculate from cycles
            avg_dead_time = self._dead_time_calculator.calculate_average_dead_time(heating_cycles)
            if avg_dead_time is not None and avg_dead_time > 0:
                effective_dead_time = avg_dead_time
                _LOGGER.info(
                    "Learned dead_time from %d cycles: %.1f minutes",
                    len(heating_cycles),
                    effective_dead_time,
                )
            else:
                effective_dead_time = self._dead_time_minutes
                _LOGGER.debug(
                    "No valid learned dead_time, using configured value: %.1f minutes",
                    effective_dead_time,
                )
        else:
            # Auto-learning disabled or no cycles: use configured value
            effective_dead_time = self._dead_time_minutes
            _LOGGER.debug(
                "Using configured dead_time: %.1f minutes (auto_learning=%s)",
                effective_dead_time,
                self._auto_learning,
            )

        return heating_cycles, contextual_lhs, effective_dead_time

    async def _get_contextual_lhs(self, target_time: datetime) -> float:
        """Get contextual LHS using detected HeatingCycles with optional cache.

        DEPRECATED: Use _get_cycles_and_calculate_parameters instead to avoid duplicate extraction.
        This method is kept for backward compatibility but now delegates to the consolidated method.

        Args:
            target_time: Target schedule time

        Returns:
            Contextual LHS in °C/h or global LHS as fallback
        """
        _, lhs, _ = await self._get_cycles_and_calculate_parameters(target_time)
        return lhs

    async def _get_effective_dead_time(self, target_time: datetime) -> float:
        """Get effective dead_time (learned or configured).

        DEPRECATED: Use _get_cycles_and_calculate_parameters instead to avoid duplicate extraction.
        This method is kept for backward compatibility but now delegates to the consolidated method.

        Args:
            target_time: Target schedule time

        Returns:
            Dead time in minutes
        """
        _, _, dead_time = await self._get_cycles_and_calculate_parameters(target_time)
        return dead_time

    async def _get_cycles_with_cache(
        self,
        device_id: str,
        target_time: datetime,
    ) -> list[HeatingCycle]:
        """Get heating cycles using cache with incremental updates.

        Args:
            device_id: Device identifier
            target_time: Current target time

        Returns:
            List of heating cycles within retention period
        """
        _LOGGER.debug("Entering _get_cycles_with_cache")
        _LOGGER.debug(
            "Getting cycles with cache for device=%s, target_time=%s",
            device_id,
            target_time,
        )

        # Get existing cache data
        cache_data = await self._cycle_cache.get_cache_data(device_id)  # type: ignore[union-attr]

        if cache_data:
            _LOGGER.debug(
                "Found cache with %d cycles, last_search_time=%s",
                cache_data.cycle_count,
                cache_data.last_search_time,
            )

            # Only search for new cycles if last search was more than 24 hours ago
            time_since_last_search = target_time - cache_data.last_search_time
            hours_since_last_search = time_since_last_search.total_seconds() / 3600

            if hours_since_last_search < 24:
                _LOGGER.debug(
                    "Last search was %.1f hours ago (< 24h), using cached cycles without new search",
                    hours_since_last_search,
                )
                # Prune old cycles and return cached data
                await self._cycle_cache.prune_old_cycles(device_id, target_time)  # type: ignore[union-attr]
                updated_cache = await self._cycle_cache.get_cache_data(device_id)  # type: ignore[union-attr]
                if updated_cache:
                    cycles = updated_cache.get_cycles_within_retention(target_time)
                    _LOGGER.debug("Returning %d cached cycles within retention", len(cycles))
                    _LOGGER.debug("Exiting _get_cycles_with_cache")
                    return cycles
                return []

            _LOGGER.info(
                "Last search was %.1f hours ago (>= 24h), searching for new cycles",
                hours_since_last_search,
            )

            # Determine incremental search period from last_search_time to now
            search_start = cache_data.last_search_time
            search_end = target_time

            _LOGGER.debug(
                "Extracting new cycles from %s to %s",
                search_start,
                search_end,
            )

            # Extract new cycles from recorder
            new_cycles = await self._extract_cycles_from_recorder(
                device_id,
                search_start,
                search_end,
            )

            # Append new cycles to cache
            if new_cycles:
                _LOGGER.debug("Appending %d new cycles to cache", len(new_cycles))
            await self._cycle_cache.append_cycles(  # type: ignore[union-attr]
                device_id,
                new_cycles,
                search_end,
            )

            # Prune old cycles
            await self._cycle_cache.prune_old_cycles(device_id, target_time)  # type: ignore[union-attr]

            # Get updated cache data
            updated_cache = await self._cycle_cache.get_cache_data(device_id)  # type: ignore[union-attr]
            if updated_cache:
                cycles = updated_cache.get_cycles_within_retention(target_time)
                _LOGGER.debug("Returning %d cycles within retention", len(cycles))
                _LOGGER.debug("Exiting _get_cycles_with_cache")
                return cycles
            return []
        else:
            _LOGGER.info("No cache found, performing initial extraction")

            # No cache exists, perform full extraction
            search_start = target_time - timedelta(days=self._history_lookback_days)
            search_end = target_time

            cycles = await self._extract_cycles_from_recorder(
                device_id,
                search_start,
                search_end,
            )

            # Initialize cache with extracted cycles
            if cycles:
                _LOGGER.debug("Initializing cache with %d cycles", len(cycles))
            await self._cycle_cache.append_cycles(  # type: ignore[union-attr]
                device_id,
                cycles,
                search_end,
            )

            _LOGGER.debug("Exiting _get_cycles_with_cache")
            return cycles

    async def _extract_cycles_from_recorder(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract heating cycles directly from Home Assistant recorder.

        Args:
            device_id: Device identifier
            start_time: Start of search period
            end_time: End of search period

        Returns:
            List of extracted heating cycles
        """
        _LOGGER.debug("Entering _extract_cycles_from_recorder")
        _LOGGER.debug(
            "Extracting cycles for device=%s from %s to %s",
            device_id,
            start_time,
            end_time,
        )

        # Try to build a HistoricalDataSet from HA adapters (climate/sensors)
        # so we can extract HeatingCycles in the specified period.
        try:
            from ..infrastructure.adapters import (
                ClimateDataAdapter,
                SensorDataAdapter,
            )
        except ImportError:
            _LOGGER.warning("Data adapters not available")
            _LOGGER.debug("Exiting _extract_cycles_from_recorder")
            return []

        heating_cycles: list[HeatingCycle] = []

        hass = self._environment_context_reader.get_hass()
        indoor_humidity_id = self._environment_context_reader.get_humidity_in_entity_id()
        outdoor_humidity_id = self._environment_context_reader.get_humidity_out_entity_id()

        combined_data: dict[HistoricalDataKey, list] = {}

        # Fetch climate data (indoor temp, target temp, heating state)
        # Add small delays between fetches to yield control to event loop
        try:
            climate_adapter = ClimateDataAdapter(hass)
            indoor_data = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(indoor_data.data)
            await asyncio.sleep(1)  # Yield to event loop

            target_data = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.TARGET_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(target_data.data)
            await asyncio.sleep(1)  # Yield to event loop

            heating_state = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.HEATING_STATE,
                start_time,
                end_time,
            )
            combined_data.update(heating_state.data)
            await asyncio.sleep(1)  # Yield to event loop
        except Exception as exc:
            _LOGGER.warning("Failed to fetch climate historical data: %s", exc)
            _LOGGER.debug("Exiting _extract_cycles_from_recorder")
            return []

        # Optional sensors
        sensor_adapter = SensorDataAdapter(hass)
        if indoor_humidity_id:
            try:
                humidity_in = await sensor_adapter.fetch_historical_data(
                    indoor_humidity_id,
                    HistoricalDataKey.INDOOR_HUMIDITY,
                    start_time,
                    end_time,
                )
                combined_data.update(humidity_in.data)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch indoor humidity history: %s", exc)
            await asyncio.sleep(1)  # Yield to event loop
        if outdoor_humidity_id:
            try:
                humidity_out = await sensor_adapter.fetch_historical_data(
                    outdoor_humidity_id,
                    HistoricalDataKey.OUTDOOR_HUMIDITY,
                    start_time,
                    end_time,
                )
                combined_data.update(humidity_out.data)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch outdoor humidity history: %s", exc)
            await asyncio.sleep(1)  # Yield to event loop
        # Construct dataset and extract cycles
        historical_data_set = HistoricalDataSet(data=combined_data)
        try:
            heating_cycles = await self._heating_cycle_service.extract_heating_cycles(
                device_id=device_id,
                history_data_set=historical_data_set,
                start_time=start_time,
                end_time=end_time,
            )
        except ValueError as exc:
            _LOGGER.warning(
                "Cannot extract heating cycles: %s",
                exc,
            )
            heating_cycles = []

        _LOGGER.debug("Extracted %d cycles from recorder", len(heating_cycles))
        _LOGGER.debug("Exiting _extract_cycles_from_recorder")
        return heating_cycles

    async def calculate_and_schedule_anticipation(self, ihp_enabled: bool = True) -> dict | None:
        """Calculate anticipation and schedule heating start.

        Args:
            ihp_enabled: Whether IHP preheating is enabled. When False, calculations
                        continue but scheduler commands are skipped.

        Returns:
            Dict with anticipation data for sensors, or None if not applicable.
            When scheduler is not configured or no timeslot is available,
            returns a dict with clear_values=True to reset sensors to unknown state.
        """
        # Get next timeslot first to check if any scheduler is configured
        timeslot = await self._scheduler_reader.get_next_timeslot()

        # If no timeslot and no active scheduler, it means no scheduler was ever configured
        if not timeslot and not self._active_scheduler_entity:
            _LOGGER.debug("No scheduler configured for this device")
            # Return clear_values dict to reset sensors to unknown
            return {"clear_values": True}

        # Check if the currently tracked scheduler has been disabled
        if self._active_scheduler_entity and not await self._scheduler_reader.is_scheduler_enabled(
            self._active_scheduler_entity
        ):
            _LOGGER.warning(
                "Active scheduler %s has been disabled. Clearing anticipation state.",
                self._active_scheduler_entity,
            )
            await self._clear_anticipation_state()
            # Return clear_values dict to reset sensors to unknown
            return {"clear_values": True}

        # No timeslot available (scheduler was configured but now disabled or no valid timeslot)
        if not timeslot:
            _LOGGER.debug("No scheduled timeslot found")
            # Clear all tracking state when no timeslot is available
            if (
                self._is_preheating_active
                or self._active_scheduler_entity
                or self._preheating_target_time
            ):
                _LOGGER.info("Clearing anticipation state (no timeslot available)")
                await self._clear_anticipation_state()
            # Return clear_values dict to reset sensors to unknown
            return {"clear_values": True}

        # Get current environment
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            _LOGGER.warning("Cannot read current environment")
            return None

        # Get contextual LHS and effective dead_time (consolidated to avoid duplicate extraction)
        _, lhs, dead_time = await self._get_cycles_and_calculate_parameters(timeslot.target_time)

        # Check if already at target
        if environment.indoor_temperature >= timeslot.target_temp:
            _LOGGER.debug(
                "Already at target (%.1f°C >= %.1f°C)",
                environment.indoor_temperature,
                timeslot.target_temp,
            )
            self._is_preheating_active = False
            self._preheating_target_time = None
            return {
                "anticipated_start_time": timeslot.target_time,
                "next_schedule_time": timeslot.target_time,
                "next_target_temperature": timeslot.target_temp,
                "anticipation_minutes": 0,
                "current_temp": environment.indoor_temperature,
                "learned_heating_slope": lhs,
                "confidence_level": 100,
                "timeslot_id": timeslot.timeslot_id,
                "scheduler_entity": timeslot.scheduler_entity,
            }

        # Calculate prediction
        prediction = self._prediction_service.predict_heating_time(
            current_temp=environment.indoor_temperature,
            target_temp=timeslot.target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.indoor_humidity,
            learned_slope=lhs,
            target_time=timeslot.target_time,
            cloud_coverage=environment.cloud_coverage,
            dead_time_minutes=dead_time,
        )

        _LOGGER.info(
            "Anticipation: start at %s (%.1f min) for target %.1f°C at %s (LHS: %.2f°C/h, confidence: %.2f)",
            prediction.anticipated_start_time.isoformat(),
            prediction.estimated_duration_minutes,
            timeslot.target_temp,
            timeslot.target_time.isoformat(),
            prediction.learned_heating_slope,
            prediction.confidence_level,
        )

        # Track the active scheduler entity (for later disable detection)
        # This must be set BEFORE calling _schedule_anticipation so that
        # subsequent disable events can be properly detected
        if self._active_scheduler_entity != timeslot.scheduler_entity:
            _LOGGER.debug("Tracking scheduler entity: %s", timeslot.scheduler_entity)
            self._active_scheduler_entity = timeslot.scheduler_entity

        # Schedule if needed (only if IHP is enabled)
        if ihp_enabled:
            await self._schedule_anticipation(
                anticipated_start=prediction.anticipated_start_time,
                target_time=timeslot.target_time,
                target_temp=timeslot.target_temp,
                scheduler_entity_id=timeslot.scheduler_entity,
                lhs=prediction.learned_heating_slope,
            )
        else:
            # IHP disabled - revert to standard scenario if preheating was active
            if self._is_preheating_active:
                _LOGGER.info(
                    "IHP disabled while preheating active - reverting to current scheduled state"
                )
                # Call cancel_action to revert thermostat to current time's preset/temperature
                await self._scheduler_commander.cancel_action(timeslot.scheduler_entity)
            else:
                _LOGGER.debug("IHP disabled - no active preheating to revert")

            # Clear anticipation state (MUST await to cancel active timer immediately)
            await self._clear_anticipation_state()

        # Return data for sensors
        return {
            "anticipated_start_time": prediction.anticipated_start_time,
            "next_schedule_time": timeslot.target_time,
            "next_target_temperature": timeslot.target_temp,
            "anticipation_minutes": prediction.estimated_duration_minutes,
            "current_temp": environment.indoor_temperature,
            "learned_heating_slope": prediction.learned_heating_slope,
            "confidence_level": prediction.confidence_level,
            "timeslot_id": timeslot.timeslot_id,
            "scheduler_entity": timeslot.scheduler_entity,
        }

    async def _schedule_anticipation(
        self,
        anticipated_start: datetime,
        target_time: datetime,
        target_temp: float,
        scheduler_entity_id: str,
        lhs: float,
    ) -> None:
        """Schedule anticipated heating start using timer and handle revert logic.

        This method uses a timer to trigger anticipation at the exact anticipated start time,
        independent of climate entity state changes. It also handles reverting to the current
        scheduled state when conditions change (e.g., anticipated start time moves later).

        Args:
            anticipated_start: When to start heating
            target_time: Target schedule time
            target_temp: Target temperature
            scheduler_entity_id: Scheduler entity to trigger
            lhs: Learned heating slope used
        """
        now = dt_util.now()

        # Check if scheduler is enabled before proceeding
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning(
                "Scheduler %s is disabled. Skipping anticipation scheduling.", scheduler_entity_id
            )
            # If we were tracking this scheduler, clear the state
            if self._active_scheduler_entity == scheduler_entity_id:
                await self._clear_anticipation_state()
            return

        # Only if scheduler is enabled, check if we're currently pre-heating and should revert
        if self._is_preheating_active:
            # If anticipated start moved to the future (after now), we should stop pre-heating
            if anticipated_start > now and self._preheating_target_time == target_time:
                _LOGGER.info(
                    "Anticipated start time moved later (now: %s, new start: %s). "
                    "LHS improved from %.2f to %.2f°C/h. Reverting to current scheduled state.",
                    now.isoformat(),
                    anticipated_start.isoformat(),
                    self._last_scheduled_lhs or 0.0,
                    lhs,
                )

                await self._scheduler_commander.cancel_action(scheduler_entity_id)

                # Update tracking for new anticipated time and schedule timer
                self._last_scheduled_time = anticipated_start
                self._last_scheduled_lhs = lhs
                self._is_preheating_active = False
                self._preheating_target_time = None

                # Schedule timer for the new anticipated time
                await self._schedule_anticipation_timer(
                    anticipated_start,
                    target_time,
                    target_temp,
                    scheduler_entity_id,
                )
                return

            # If we've reached the target time, mark pre-heating as complete
            if now >= target_time:
                _LOGGER.info("Target time reached, pre-heating complete")
                await self._clear_anticipation_state()
                return

        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs

        # If anticipated start is in past but target is future, trigger now
        # This handles both: not yet preheating OR already preheating but with past anticipation
        if anticipated_start <= now < target_time:
            if not self._is_preheating_active:
                _LOGGER.info(
                    "Anticipated start %s is past, triggering pre-heating immediately",
                    anticipated_start.isoformat(),
                )
                # Use ONLY the scheduler's run_action - it will handle VTherm state correctly
                # Respects scheduler conditions (skip_conditions=False in the adapter)
                await self._scheduler_commander.run_action(target_time, scheduler_entity_id)
                self._is_preheating_active = True
                self._preheating_target_time = target_time
                self._active_scheduler_entity = scheduler_entity_id
            else:
                # Already preheating but anticipation is past - ensure we stay in preheating
                _LOGGER.debug(
                    "Already preheating (started earlier), continuation through target time %s",
                    target_time.isoformat(),
                )
            return

        # If both are in past, skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are past, skipping")
            await self._cancel_anticipation_timer()
            return
        # Anticipated start is in the future - schedule timer to trigger it.
        # We always (re)schedule here so that the timer reflects the most recent
        # anticipated start time, even if pre-heating is already active.
        await self._schedule_anticipation_timer(
            anticipated_start,
            target_time,
            target_temp,
            scheduler_entity_id,
        )

    async def check_overshoot_risk(self, scheduler_entity_id: str) -> None:
        """Check if heating should stop to prevent overshoot."""
        # Get next timeslot
        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            return

        # Get current environment and slope
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            return

        current_slope = self._climate_data_reader.get_current_slope()
        if current_slope is None or current_slope <= 0.0:
            return

        # Calculate estimated temperature at target time
        now = dt_util.now()
        if now >= timeslot.target_time:
            return

        time_to_target = (timeslot.target_time - now).total_seconds() / 3600.0
        estimated_temp = environment.indoor_temperature + (current_slope * time_to_target)

        # Check overshoot threshold
        overshoot_threshold = timeslot.target_temp + 0.5

        if estimated_temp >= overshoot_threshold and self._is_preheating_active:
            _LOGGER.info(
                "Overshoot risk! Current: %.1f°C, estimated: %.1f°C, target: %.1f°C - reverting to current schedule",
                environment.indoor_temperature,
                estimated_temp,
                timeslot.target_temp,
            )
            # Check scheduler is enabled before calling cancel_action
            if await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
                # Revert to current scheduled state instead of directly turning off
                # This respects scheduler conditions and returns to the proper setpoint
                await self._scheduler_commander.cancel_action(scheduler_entity_id)
            else:
                _LOGGER.warning(
                    "Scheduler %s is disabled. Cannot cancel action for overshoot prevention.",
                    scheduler_entity_id,
                )
            await self._clear_anticipation_state()

    async def reset_learned_slopes(self) -> None:
        """Reset all learned slope history."""
        _LOGGER.info("Resetting learned heating slope history")
        await self._model_storage.clear_slope_history()

    def get_heating_cycle_service(self) -> HeatingCycleService:
        """Get the heating cycle service for use case instantiation.

        This exposes the private heating_cycle_service to allow external
        code (particularly factories) to access the configured domain service.

        Returns:
            IHeatingCycleService implementation
        """
        _LOGGER.debug("Exporting heating_cycle_service to external consumer")
        return self._heating_cycle_service

    def get_global_lhs_calculator(self) -> GlobalLHSCalculatorService:
        """Get the global LHS calculator for lifecycle wiring."""
        _LOGGER.debug("Exporting global_lhs_calculator to external consumer")
        return self._global_lhs_calculator

    def get_contextual_lhs_calculator(self) -> ContextualLHSCalculatorService:
        """Get the contextual LHS calculator for lifecycle wiring."""
        _LOGGER.debug("Exporting contextual_lhs_calculator to external consumer")
        return self._contextual_lhs_calculator

    def set_heating_cycle_lifecycle_manager(
        self,
        manager: HeatingCycleLifecycleManager,
    ) -> None:
        """Attach the heating cycle lifecycle manager."""
        self._heating_cycle_lifecycle_manager = manager

    def set_lhs_lifecycle_manager(self, manager: LhsLifecycleManager) -> None:
        """Attach the LHS lifecycle manager."""
        self._lhs_lifecycle_manager = manager
