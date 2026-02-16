"""Application service - orchestrates domain and infrastructure.

This service coordinates between the domain layer (HeatingPilot, PredictionService)
and infrastructure adapters, implementing use cases.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable

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
