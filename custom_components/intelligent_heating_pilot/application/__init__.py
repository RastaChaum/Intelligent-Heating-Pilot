"""Application service - orchestrates domain and infrastructure.

This service coordinates between the domain layer (HeatingPilot, PredictionService)
and infrastructure adapters, implementing use cases.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..domain.entities import HeatingPilot
from ..domain.services import PredictionService, LHSCalculationService, HeatingCycleService
from ..domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
    HeatingCycle,
)
from ..infrastructure.decision_strategy_factory import DecisionStrategyFactory
from ..const import DEFAULT_DECISION_MODE, DEFAULT_DATA_RETENTION_DAYS

if TYPE_CHECKING:
    from ..infrastructure.adapters import (
        HAClimateCommander,
        HAEnvironmentReader,
        HAModelStorage,
        HASchedulerCommander,
        HASchedulerReader,
        HACycleCache,
    )

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
        scheduler_reader: "HASchedulerReader",
        model_storage: "HAModelStorage",
        scheduler_commander: "HASchedulerCommander",
        climate_commander: "HAClimateCommander",
        environment_reader: "HAEnvironmentReader",
        cycle_cache: "HACycleCache | None" = None,
        lhs_window_hours: float = 6.0,
        history_lookback_days: int | None = None,
        decision_mode: str = DEFAULT_DECISION_MODE,
        temp_delta_threshold: float | None = None,
        cycle_split_duration_minutes: int | None = None,
        min_cycle_duration_minutes: int | None = None,
        max_cycle_duration_minutes: int | None = None,
    ) -> None:
        """Initialize the application service.
        
        Args:
            scheduler_reader: Reads scheduled timeslots
            model_storage: Persists learned slopes
            scheduler_commander: Triggers scheduler actions
            climate_commander: Controls climate entity
            environment_reader: Reads environmental conditions
            cycle_cache: Optional cache for heating cycles (enables incremental updates)
            lhs_window_hours: Time window in hours for contextual LHS (default: 6)
            history_lookback_days: Number of days of HA history to query
                to extract heating cycles (default: DEFAULT_DATA_RETENTION_DAYS)
            decision_mode: Decision mode ('simple' or 'ml')
            temp_delta_threshold: Temperature threshold for cycle detection (°C)
            cycle_split_duration_minutes: Duration for splitting long cycles (minutes)
            min_cycle_duration_minutes: Minimum cycle duration (minutes)
            max_cycle_duration_minutes: Maximum cycle duration (minutes)
        """
        self._scheduler_reader = scheduler_reader
        self._model_storage = model_storage
        self._scheduler_commander = scheduler_commander
        self._climate_commander = climate_commander
        self._environment_reader = environment_reader
        self._cycle_cache = cycle_cache
        self._prediction_service = PredictionService()
        self._lhs_calculation_service = LHSCalculationService()
        
        # Create HeatingCycleService with configured parameters
        from ..const import (
            DEFAULT_TEMP_DELTA_THRESHOLD,
            DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
            DEFAULT_MIN_CYCLE_DURATION_MINUTES,
            DEFAULT_MAX_CYCLE_DURATION_MINUTES,
        )
        self._heating_cycle_service = HeatingCycleService(
            temp_delta_threshold=temp_delta_threshold or DEFAULT_TEMP_DELTA_THRESHOLD,
            cycle_split_duration_minutes=cycle_split_duration_minutes,
            min_cycle_duration_minutes=min_cycle_duration_minutes or DEFAULT_MIN_CYCLE_DURATION_MINUTES,
            max_cycle_duration_minutes=max_cycle_duration_minutes or DEFAULT_MAX_CYCLE_DURATION_MINUTES,
        )
        
        self._lhs_window_hours = lhs_window_hours
        self._history_lookback_days = (
            int(history_lookback_days)
            if history_lookback_days is not None
            else int(DEFAULT_DATA_RETENTION_DAYS)
        )
        
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
    
    def _clear_anticipation_state(self) -> None:
        """Clear all anticipation tracking state."""
        self._is_preheating_active = False
        self._preheating_target_time = None
        self._last_scheduled_time = None
        self._last_scheduled_lhs = None
        self._active_scheduler_entity = None
        _LOGGER.debug("Anticipation state cleared")
    
    # NOTE: process_slope_update() removed - we now extract slopes directly from
    # Home Assistant recorder via HeatingCycleService, so no disk-based persistence needed
    
    async def _get_contextual_lhs(self, target_time: datetime) -> float:
        """Get contextual LHS using detected HeatingCycles with optional cache.
        
        When cycle_cache is available, this method:
        1. Retrieves cached cycles within retention period
        2. Determines the incremental search period (last_search_time to target_time)
        3. Extracts only new cycles from recorder
        4. Appends new cycles to cache
        5. Prunes old cycles beyond retention
        6. Calculates LHS from all cached cycles
        
        Without cache, falls back to direct recorder extraction.
        
        Args:
            target_time: Target schedule time
            
        Returns:
            Contextual LHS in °C/h or global LHS as fallback
        """
        target_hour = target_time.hour
        _LOGGER.info(
            "Computing contextual LHS for hour %02d using HeatingCycles%s",
            target_hour,
            " (with cache)" if self._cycle_cache else "",
        )
        
        # Get device ID for cache lookup
        vtherm_id = self._environment_reader.get_vtherm_entity_id()
        
        # Try to use cycle cache if available
        if self._cycle_cache:
            try:
                heating_cycles = await self._get_cycles_with_cache(vtherm_id, target_time)
            except Exception as exc:
                _LOGGER.warning(
                    "Failed to use cycle cache, falling back to direct extraction: %s",
                    exc,
                )
                heating_cycles = await self._extract_cycles_from_recorder(
                    vtherm_id,
                    target_time - timedelta(days=self._history_lookback_days),
                    target_time,
                )
        else:
            # No cache available, extract directly from recorder
            heating_cycles = await self._extract_cycles_from_recorder(
                vtherm_id,
                target_time - timedelta(days=self._history_lookback_days),
                target_time,
            )
        
        # If we have extracted cycles, compute contextual LHS (by hour)
        if heating_cycles:
            contextual_lhs = self._lhs_calculation_service.calculate_contextual_lhs(
                heating_cycles=heating_cycles,
                target_hour=target_hour,
            )
            _LOGGER.info(
                "Contextual LHS for hour %02d from %d cycles: %.2f°C/h",
                target_hour,
                len(heating_cycles),
                contextual_lhs,
            )
            return contextual_lhs

        # Fallback: if adapters unavailable or cycles empty, use global learned LHS
        global_lhs = await self._model_storage.get_learned_heating_slope()
        _LOGGER.warning(
            "No HeatingCycles available, using global LHS: %.2f°C/h",
            global_lhs,
        )
        return global_lhs
    
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
            
            _LOGGER.debug(
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
        else:
            _LOGGER.debug("No cache found, performing full extraction")
            
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

        hass = self._environment_reader.get_hass()
        indoor_humidity_id = self._environment_reader.get_humidity_in_entity_id()
        outdoor_humidity_id = self._environment_reader.get_humidity_out_entity_id()

        combined_data: dict[HistoricalDataKey, list] = {}

        # Fetch climate data (indoor temp, target temp, heating state)
        try:
            climate_adapter = ClimateDataAdapter(hass)
            indoor_data = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(indoor_data.data)

            target_data = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.TARGET_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(target_data.data)

            heating_state = await climate_adapter.fetch_historical_data(
                device_id,
                HistoricalDataKey.HEATING_STATE,
                start_time,
                end_time,
            )
            combined_data.update(heating_state.data)
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
                _LOGGER.debug("Failed to fetch indoor humidity history: %s", exc)
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
                _LOGGER.debug("Failed to fetch outdoor humidity history: %s", exc)

        # Construct dataset and extract cycles
        historical_data_set = HistoricalDataSet(data=combined_data)
        try:
            heating_cycles = await self._heating_cycle_service.extract_heating_cycles(
                device_id=device_id,
                history_data_set=historical_data_set,
                start_time=start_time,
                end_time=end_time,
                cycle_split_duration_minutes=None,
            )
        except ValueError as exc:
            _LOGGER.debug(
                "Cannot extract heating cycles: %s",
                exc,
            )
            heating_cycles = []
        
        _LOGGER.debug("Extracted %d cycles from recorder", len(heating_cycles))
        _LOGGER.debug("Exiting _extract_cycles_from_recorder")
        return heating_cycles
    
    async def calculate_and_schedule_anticipation(self) -> dict | None:
        """Calculate anticipation and schedule heating start.
        
        Returns:
            Dict with anticipation data for sensors, or None if not applicable
        """
        # Check if the currently tracked scheduler has been disabled
        if self._active_scheduler_entity:
            if not await self._scheduler_reader.is_scheduler_enabled(self._active_scheduler_entity):
                _LOGGER.warning(
                    "Active scheduler %s has been disabled. Clearing anticipation state.",
                    self._active_scheduler_entity
                )
                self._clear_anticipation_state()
                # Return None to clear sensor values
                return None
        
        # Get next timeslot
        timeslot = await self._scheduler_reader.get_next_timeslot()
        if not timeslot:
            _LOGGER.debug("No scheduled timeslot found")
            # Clear all tracking state when no timeslot is available
            # This handles both the case where the scheduler was just disabled
            # and when _active_scheduler_entity is already None
            if self._is_preheating_active or self._active_scheduler_entity or self._preheating_target_time:
                _LOGGER.info("Clearing anticipation state (no timeslot available)")
                self._clear_anticipation_state()
            return None
        
        # Get current environment
        environment = await self._environment_reader.get_current_environment()
        if not environment:
            _LOGGER.warning("Cannot read current environment")
            return None
              
        # Get contextual LHS from time window preceding target time
        lhs = await self._get_contextual_lhs(timeslot.target_time)
        
        # Check if already at target
        if environment.indoor_temperature >= timeslot.target_temp:
            _LOGGER.debug(
                "Already at target (%.1f°C >= %.1f°C)",
                environment.indoor_temperature,
                timeslot.target_temp
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
        
        # Schedule if needed
        await self._schedule_anticipation(
            anticipated_start=prediction.anticipated_start_time,
            target_time=timeslot.target_time,
            target_temp=timeslot.target_temp,
            scheduler_entity_id=timeslot.scheduler_entity,
            lhs=prediction.learned_heating_slope,
        )
        
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
        """Schedule anticipated heating start and handle revert logic.
        
        This method handles both starting pre-heating and reverting to the current
        scheduled state when conditions change (e.g., anticipated start time moves later).
        
        Args:
            anticipated_start: When to start heating
            target_time: Target schedule time
            target_temp: Target temperature
            lhs: Learned heating slope used
        """
        now = dt_util.now()
        
        # Check if scheduler is enabled before proceeding
        if not await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
            _LOGGER.warning(
                "Scheduler %s is disabled. Skipping anticipation scheduling.",
                scheduler_entity_id
            )
            # If we were tracking this scheduler, clear the state
            if self._active_scheduler_entity == scheduler_entity_id:
                self._clear_anticipation_state()
            return
        
        # Only if scheduler is enabled, check if we're currently pre-heating and should revert
        if self._is_preheating_active:
            # If anticipated start moved to the future (after now), we should stop pre-heating
            if anticipated_start > now and self._preheating_target_time == target_time:
                _LOGGER.warning(
                    "Anticipated start time moved later (now: %s, new start: %s). "
                    "LHS improved from %.2f to %.2f°C/h. Reverting to current scheduled state.",
                    now.isoformat(),
                    anticipated_start.isoformat(),
                    self._last_scheduled_lhs or 0.0,
                    lhs
                )

                await self._scheduler_commander.cancel_action(scheduler_entity_id)

                # Update tracking for new anticipated time
                self._last_scheduled_time = anticipated_start
                self._last_scheduled_lhs = lhs
                self._is_preheating_active = False
                return
            
            # If we've reached the target time, mark pre-heating as complete
            if now >= target_time:
                _LOGGER.info("Target time reached, pre-heating complete")
                self._is_preheating_active = False
                self._preheating_target_time = None
                self._active_scheduler_entity = None
                return
       
        # Update tracking
        self._last_scheduled_time = anticipated_start
        self._last_scheduled_lhs = lhs
        
        # If anticipated start is in past but target is future, trigger now
        if anticipated_start <= now < target_time and not self._is_preheating_active:
            _LOGGER.info(
                "Anticipated start %s is past, triggering pre-heating immediately",
                anticipated_start.isoformat()
            )
            # Use ONLY the scheduler's run_action - it will handle VTherm state correctly
            # Respects scheduler conditions (skip_conditions=False in the adapter)
            await self._scheduler_commander.run_action(target_time, scheduler_entity_id)
            self._is_preheating_active = True
            self._preheating_target_time = target_time
            self._active_scheduler_entity = scheduler_entity_id
            return
        
        # If both are in past, skip
        if anticipated_start <= now and target_time <= now:
            _LOGGER.debug("Both times are past, skipping")
            return
        
        # Anticipated start is in the future - wait for it
        _LOGGER.info(
            "Anticipation scheduled: start at %s for target %s (waiting %.1f minutes)",
            anticipated_start.isoformat(),
            target_time.isoformat(),
            (anticipated_start - now).total_seconds() / 60.0
        )
        # Track which scheduler we're anticipating for
        self._active_scheduler_entity = scheduler_entity_id
        # Note: Actual scheduling is triggered by periodic updates from event_bridge
    
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
        
        current_slope = self._environment_reader.get_vtherm_slope()
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
            _LOGGER.warning(
                "Overshoot risk! Current: %.1f°C, estimated: %.1f°C, target: %.1f°C - reverting to current schedule",
                environment.indoor_temperature,
                estimated_temp,
                timeslot.target_temp
            )
            # Check scheduler is enabled before calling cancel_action
            if await self._scheduler_reader.is_scheduler_enabled(scheduler_entity_id):
                # Revert to current scheduled state instead of directly turning off
                # This respects scheduler conditions and returns to the proper setpoint
                await self._scheduler_commander.cancel_action(scheduler_entity_id)
            else:
                _LOGGER.warning(
                    "Scheduler %s is disabled. Cannot cancel action for overshoot prevention.",
                    scheduler_entity_id
                )
            self._clear_anticipation_state()
    
    async def reset_learned_slopes(self) -> None:
        """Reset all learned slope history."""
        _LOGGER.info("Resetting learned heating slope history")
        await self._model_storage.clear_slope_history()
