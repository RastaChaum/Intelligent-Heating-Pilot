"""Heating application entry point and DI container for Intelligent Heating Pilot."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .application.heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager
from .application.heating_cycle_lifecycle_manager_factory import (
    HeatingCycleLifecycleManagerFactory,
)
from .application.lhs_lifecycle_manager import LhsLifecycleManager
from .application.lhs_lifecycle_manager_factory import LhsLifecycleManagerFactory
from .application.orchestrator import HeatingOrchestrator
from .application.use_cases import (
    CalculateAnticipationUseCase,
    CheckOvershootRiskUseCase,
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
    UpdateCacheDataUseCase,
)
from .const import CONF_IHP_ENABLED, DECISION_MODE_SIMPLE, DOMAIN, EVENT_DEAD_TIME_UPDATED
from .domain.interfaces.device_config_reader_interface import DeviceConfig
from .domain.services import (
    ContextualLHSCalculatorService,
    DeadTimeCalculationService,
    GlobalLHSCalculatorService,
    HeatingCycleService,
    PredictionService,
)
from .infrastructure.adapters import (
    HAClimateCommander,
    HAClimateDataReader,
    HAContextReader,
    HAEnvironmentReader,
    HAHeatingCycleStorage,
    HALhsStorage,
    HASchedulerCommander,
    HASchedulerReader,
    HATimerScheduler,
)
from .infrastructure.event_bridge import HAEventBridge

_LOGGER = logging.getLogger(__name__)


class HeatingApplication:
    """Heating application entry point and DI container.

    This class:
    - Creates and wires adapters
    - Creates application service
    - Setups event bridge
    - Exposes data for sensors (via application service)

    NO business logic - pure dependency injection and lifecycle management.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_config: DeviceConfig,
    ) -> None:
        """Initialize the coordinator with dependency injection.

        Args:
            hass: Home Assistant instance
            device_config: Complete device configuration (injected, not read from config_entry)

        NOTE: config_entry is NOT passed here. This respects DDD principles:
        - The domain/application layer does NOT depend on HA infrastructure (ConfigEntry)
        - All configuration comes from the value object (DeviceConfig)
        - For entry_id-based operations, use device_config.device_id
        """
        _LOGGER.debug("Initializing HeatingApplication with injected DeviceConfig")

        self.hass = hass
        self._device_id = device_config.device_id  # Store entry ID for adapter creation

        # Store immutable device configuration
        self._device_config = device_config

        # Extract configuration from DeviceConfig (NOT from config_entry!)
        # This is the key change: we read from the injected value object
        self._vtherm_id = device_config.vtherm_entity_id
        self._scheduler_ids = device_config.scheduler_entities
        self._humidity_in_id = device_config.humidity_in_entity_id
        self._humidity_out_id = device_config.humidity_out_entity_id
        self._temperature_out_id = device_config.temperature_out_entity_id
        self._cloud_cover_id = device_config.cloud_cover_entity_id
        self._data_retention_days = device_config.lhs_retention_days
        self._decision_mode = DECISION_MODE_SIMPLE

        # Heating cycle detection parameters
        self._temp_delta_threshold = device_config.temp_delta_threshold
        self._cycle_split_duration_minutes = device_config.cycle_split_duration_minutes
        self._min_cycle_duration_minutes = device_config.min_cycle_duration_minutes
        self._max_cycle_duration_minutes = device_config.max_cycle_duration_minutes
        self._dead_time_minutes = device_config.dead_time_minutes
        self._auto_learning = device_config.auto_learning

        # IHP enabled state
        self._ihp_enabled = device_config.ihp_enabled

        # Infrastructure adapters
        self._lhs_storage: HALhsStorage | None = None
        self._cycle_storage: HAHeatingCycleStorage | None = None
        self._scheduler_reader: HASchedulerReader | None = None
        self._scheduler_commander: HASchedulerCommander | None = None
        self._climate_commander: HAClimateCommander | None = None
        self._environment_reader: HAEnvironmentReader | None = None
        self._context_reader: HAContextReader | None = None
        self._climate_data_reader: HAClimateDataReader | None = None
        self._timer_scheduler: HATimerScheduler | None = None

        # Orchestrator (coordinates use cases)
        self._orchestrator: Any | None = None

        # Lifecycle managers
        self._heating_cycle_manager: HeatingCycleLifecycleManager | None = None
        self._lhs_manager: LhsLifecycleManager | None = None

        # Event bridge
        self._event_bridge: HAEventBridge | None = None

        # Cached data for sensors (refreshed by application service)
        self._last_anticipation_data: dict[str, Any] | None = None
        self._lhs_cache: float = 2.0  # Default global LHS
        self._contextual_lhs_cache: dict[int, float] = {}  # Contextual LHS by hour (0-23)

        # Config entry for options updates (set later via setup_config_entry_access)
        self._config_entry: ConfigEntry | None = None
        self._options_snapshot: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load and initialize all components."""
        # Create infrastructure adapters
        self._lhs_storage = HALhsStorage(
            self.hass, self._device_id, retention_days=self._data_retention_days
        )

        # Create cycle cache for incremental cycle extraction
        self._cycle_storage = HAHeatingCycleStorage(
            self.hass, self._device_id, retention_days=self._data_retention_days
        )

        self._scheduler_reader = HASchedulerReader(
            self.hass,
            self._scheduler_ids,
            vtherm_entity_id=self._vtherm_id,
        )

        self._scheduler_commander = HASchedulerCommander(self.hass)

        self._climate_commander = HAClimateCommander(self.hass, self._vtherm_id)
        self._environment_reader = HAEnvironmentReader(
            self.hass,
            self._vtherm_id,
            outdoor_temp_entity_id=self._temperature_out_id,
            humidity_in_entity_id=self._humidity_in_id,
            humidity_out_entity_id=self._humidity_out_id,
            cloud_cover_entity_id=self._cloud_cover_id,
        )
        self._context_reader = HAContextReader(
            self.hass,
            outdoor_temp_entity_id=self._temperature_out_id,
            humidity_in_entity_id=self._humidity_in_id,
            humidity_out_entity_id=self._humidity_out_id,
            cloud_cover_entity_id=self._cloud_cover_id,
        )
        # Import recorder queue for HAClimateDataReader
        from .infrastructure.recorder_queue import get_recorder_queue

        self._climate_data_reader = HAClimateDataReader(
            self.hass, get_recorder_queue(self.hass), self._vtherm_id
        )

        # Create timer scheduler adapter
        self._timer_scheduler = HATimerScheduler(self.hass)

        # Create domain services (they're stateless, can be created once)
        heating_cycle_service = HeatingCycleService(
            temp_delta_threshold=self._temp_delta_threshold,
            cycle_split_duration_minutes=self._cycle_split_duration_minutes,
            min_cycle_duration_minutes=self._min_cycle_duration_minutes,
            max_cycle_duration_minutes=self._max_cycle_duration_minutes,
        )
        global_lhs_calculator = GlobalLHSCalculatorService()
        contextual_lhs_calculator = ContextualLHSCalculatorService()

        # Create lifecycle managers
        self._heating_cycle_manager = HeatingCycleLifecycleManagerFactory.create(
            hass=self.hass,
            device_config=self._device_config,
            heating_cycle_service=heating_cycle_service,
            cycle_cache=self._cycle_storage,
            timer_scheduler=self._timer_scheduler,
            model_storage=self._lhs_storage,
            dead_time_updated_callback=self._fire_dead_time_updated_event,
        )

        self._lhs_manager = LhsLifecycleManagerFactory.create(
            model_storage=self._lhs_storage,
            global_lhs_calculator=global_lhs_calculator,
            contextual_lhs_calculator=contextual_lhs_calculator,
            timer_scheduler=self._timer_scheduler,
        )

        # Create use cases for orchestrator
        _LOGGER.debug("Creating use cases for orchestrator")

        # Create services directly (they're simple domain services, not state-dependent)
        prediction_service = PredictionService()
        dead_time_calculator = DeadTimeCalculationService()

        calculate_anticipation = CalculateAnticipationUseCase(
            scheduler_reader=self._scheduler_reader,
            environment_reader=self._environment_reader,
            climate_data_reader=self._climate_data_reader,
            heating_cycle_manager=self._heating_cycle_manager,
            lhs_lifecycle_manager=self._lhs_manager,
            prediction_service=prediction_service,
            dead_time_calculator=dead_time_calculator,
            auto_learning=self._auto_learning,
            default_dead_time_minutes=self._dead_time_minutes,
        )

        control_preheating = ControlPreheatingUseCase(
            scheduler_commander=self._scheduler_commander,
        )

        schedule_anticipation_action = ScheduleAnticipationActionUseCase(
            scheduler_reader=self._scheduler_reader,
            scheduler_commander=self._scheduler_commander,
            timer_scheduler=self._timer_scheduler,
            control_preheating_use_case=control_preheating,  # Delegate state management
        )

        check_overshoot_risk = CheckOvershootRiskUseCase(
            scheduler_reader=self._scheduler_reader,
            environment_reader=self._environment_reader,
            climate_data_reader=self._climate_data_reader,
            control_preheating=control_preheating,
        )

        update_cache = UpdateCacheDataUseCase(
            cycle_storage=self._cycle_storage,
            lhs_storage=self._lhs_storage,
            lhs_lifecycle_manager=self._lhs_manager,
        )

        # Create orchestrator
        self._orchestrator = HeatingOrchestrator(
            calculate_anticipation=calculate_anticipation,
            control_preheating=control_preheating,
            schedule_anticipation_action=schedule_anticipation_action,
            check_overshoot_risk=check_overshoot_risk,
            update_cache=update_cache,
        )
        _LOGGER.debug("Orchestrator created successfully")

        # Create event bridge
        monitored_entities = []
        if self._humidity_in_id:
            monitored_entities.append(self._humidity_in_id)
        if self._humidity_out_id:
            monitored_entities.append(self._humidity_out_id)
        if self._cloud_cover_id:
            monitored_entities.append(self._cloud_cover_id)

        self._event_bridge = HAEventBridge(
            self.hass,
            self._orchestrator,
            self._vtherm_id,
            self._scheduler_ids,
            monitored_entities,
            entry_id=self._device_id,
            get_ihp_enabled_func=self.is_ihp_enabled,
        )

        # Load initial data
        if self._lhs_manager:
            self._lhs_cache = await self._lhs_manager.get_global_lhs()
            # Also load contextual LHS cache for all hours
            await self._load_contextual_lhs_cache()

        # NOTE: Cycle extraction is deferred to async_initialize_cycle_extraction()
        # which is called after HA fully started (EVENT_HOMEASSISTANT_STARTED)
        # to ensure VTherm entity is available before querying its history.
        # See __init__.py async_setup_entry for the deferred initialization logic.

        _LOGGER.info(
            "[%s] Coordinator initialized (VTherm: %s, Schedulers: %d)",
            self._device_id,
            self._vtherm_id,
            len(self._scheduler_ids),
        )

        # NOTE: Initial update is now deferred to async_setup_entry to avoid blocking
        # the config flow during device creation (prevents HA watchdog restart).
        # See async_setup_entry for the deferred update logic.

    async def _load_contextual_lhs_cache(self) -> None:
        """Load contextual LHS values for all hours from storage.

        This populates the synchronous cache with contextual LHS values
        that were previously calculated and stored.
        """
        if not self._lhs_manager:
            return

        try:
            # Load contextual LHS for all 24 hours
            for hour in range(24):
                contextual_lhs = await self._lhs_manager.get_contextual_lhs(
                    target_time=dt_util.now().replace(hour=hour, minute=0, second=0, microsecond=0),
                    cycles=[],  # Empty cycles - will use stored cache
                )
                if contextual_lhs is not None and contextual_lhs != 2.0:  # 2.0 is default value
                    self._contextual_lhs_cache[hour] = contextual_lhs
                    _LOGGER.debug(
                        "Loaded contextual LHS from storage: hour %d = %.2f °C/h",
                        hour,
                        contextual_lhs,
                    )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Failed to load contextual LHS cache: %s", exc, exc_info=True)

    def setup_config_entry_access(self, config_entry: ConfigEntry) -> None:
        """Set config_entry reference for options updates.

        This is called after async_load to enable set_ihp_enabled to persist
        state changes back to the config entry.

        Args:
            config_entry: The config entry for this device
        """
        self._config_entry = config_entry

    def setup_listeners(self) -> None:
        """Setup event listeners via event bridge."""
        if self._event_bridge:
            self._event_bridge.setup_listeners()

    async def async_initialize_cycle_extraction(self) -> None:
        """Initialize cycle extraction and schedule 24h periodic refresh.

        This method MUST be called after EVENT_HOMEASSISTANT_STARTED to ensure
        the VTherm entity is available before querying its history.

        This method:
        - Verifies VTherm entity is available
        - Performs initial extraction over retention window
        - Schedules 24h periodic refresh timer
        - Logs initialization with retention days
        """
        _LOGGER.debug("Entering async_initialize_cycle_extraction for device=%s", self._device_id)

        try:
            # Check if cycle extraction is enabled
            if self._data_retention_days <= 0:
                _LOGGER.debug(
                    "Cycle extraction disabled (history_lookback_days=%d)",
                    self._data_retention_days,
                )
                return

            # Sanity checks
            if not self._device_config:
                _LOGGER.warning("Cannot initialize cycle refresh: device_config not available")
                return

            if not self._heating_cycle_manager:
                _LOGGER.warning("Cannot initialize cycle refresh: manager not available")
                return

            # Verify VTherm entity exists before attempting to query its history
            vtherm_state = self.hass.states.get(self._vtherm_id)
            if vtherm_state is None:
                _LOGGER.error(
                    "Cannot initialize cycle extraction: VTherm entity %s not found. "
                    "Ensure the climate entity is loaded before IHP starts.",
                    self._vtherm_id,
                )
                return

            # Calculate initial extraction window
            now = dt_util.utcnow()
            start_time = now - timedelta(days=self._data_retention_days)

            _LOGGER.debug(
                "Initializing cycle extraction: device_id=%s, window=%s to %s, retention=%d days",
                self._device_config.device_id,
                start_time,
                now,
                self._data_retention_days,
            )

            # Execute initial extraction + schedule 24h timer
            extracted_cycles = await self._heating_cycle_manager.startup(
                device_id=self._device_config.device_id,
                start_time=start_time,
                end_time=now,
            )

            # Update global LHS from extracted cycles (if any)
            if extracted_cycles and self._lhs_manager:
                await self._lhs_manager.update_global_lhs_from_cycles(extracted_cycles)

            _LOGGER.info(
                "Cycle extraction initialized: device=%s, retention=%d days, cycles=%d",
                self._device_config.device_id,
                self._data_retention_days,
                len(extracted_cycles),
            )

            _LOGGER.debug(
                "Exiting async_initialize_cycle_extraction for device=%s", self._device_id
            )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Failed to initialize cycle extraction for %s: %s",
                self._vtherm_id,
                err,
                exc_info=True,
            )

    async def _update_global_lhs_from_cycles(self, cycles: list) -> None:
        """Update global LHS in model storage from extracted cycles.

        This method calculates the global learned heating slope (LHS) from
        all extracted cycles and persists it to model storage for later use
        as a fallback when no contextual data is available.

        Args:
            cycles: List of HeatingCycle objects
        """
        if not cycles or not self._lhs_manager:
            return

        try:
            global_lhs = await self._lhs_manager.update_global_lhs_from_cycles(cycles)

            # Refresh cache so sensors reflect updated value
            await self.refresh_caches()

            _LOGGER.info(
                "Updated global LHS from %d cycles: %.2f°C/h",
                len(cycles),
                global_lhs,
            )

        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to update global LHS from cycles: %s",
                exc,
                exc_info=True,
            )

    async def async_notify_retention_change(self, new_retention_days: int) -> None:
        """Handle configuration change for retention/history lookback.

        Called from config flow when history_lookback_days changes.

        Args:
            new_retention_days: New retention window in days
        """
        _LOGGER.debug(
            "Retention change notification: old=%d, new=%d",
            self._data_retention_days,
            new_retention_days,
        )

        try:
            # Update stored retention days
            self._data_retention_days = new_retention_days

            # Delegate to use case for reconfiguration handling
            if self._heating_cycle_manager:
                await self._heating_cycle_manager.on_retention_change(new_retention_days)
            else:
                _LOGGER.debug("No active cycle manager; cannot propagate retention change")

            # Note: LhsLifecycleManager receives cycles from HeatingCycleLifecycleManager
            # No need to call on_retention_change directly since cascade handles it

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Error handling retention change: %s", err, exc_info=True)

    async def async_update(self) -> None:
        """Trigger anticipation calculation and cache results for sensors."""
        if not self._orchestrator:
            return

        # Calculate and schedule via orchestrator (passing IHP enabled state)
        anticipation_data = await self._orchestrator.calculate_and_schedule_anticipation(
            ihp_enabled=self._ihp_enabled
        )

        # Cache for sensors
        self._last_anticipation_data = anticipation_data

        # Refresh LHS caches
        if self._lhs_manager:
            self._lhs_cache = await self._lhs_manager.get_global_lhs()

            # Reload contextual LHS cache for the scheduled hour only (optimization)
            if anticipation_data and anticipation_data.get("next_schedule_time") is not None:
                next_schedule_time = anticipation_data.get("next_schedule_time")
                if next_schedule_time:
                    scheduled_hour = next_schedule_time.hour
                    try:
                        contextual_lhs = await self._lhs_manager.get_contextual_lhs(
                            target_time=next_schedule_time,
                            cycles=[],  # Empty cycles - will use stored cache
                        )
                        if contextual_lhs is not None and contextual_lhs != 2.0:
                            self._contextual_lhs_cache[scheduled_hour] = contextual_lhs
                            _LOGGER.debug(
                                "Updated contextual LHS cache: hour %d = %.2f °C/h",
                                scheduled_hour,
                                contextual_lhs,
                            )
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.debug("Failed to update contextual LHS cache: %s", exc)

        # Fire event for sensors
        if anticipation_data:
            # Always publish complete structure with None values for missing data
            anticipated_start = anticipation_data.get("anticipated_start_time")
            next_schedule = anticipation_data.get("next_schedule_time")

            event_data = {
                "entry_id": self._device_id,
                "anticipated_start_time": anticipated_start.isoformat()
                if anticipated_start
                else None,
                "next_schedule_time": next_schedule.isoformat() if next_schedule else None,
                "next_target_temperature": anticipation_data.get("next_target_temperature"),
                "anticipation_minutes": anticipation_data.get("anticipation_minutes"),
                "current_temp": anticipation_data.get("current_temp"),
                "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
                "confidence_level": anticipation_data.get("confidence_level"),
                "scheduler_entity": anticipation_data.get("scheduler_entity", ""),
            }
            self.hass.bus.async_fire(
                f"{DOMAIN}_anticipation_calculated",
                event_data,
            )

    def _fire_dead_time_updated_event(self, learned_dead_time: float) -> None:
        """Publish an event when learned dead time is persisted."""
        _LOGGER.debug(
            "Publishing dead time update for entry_id=%s: %.1f minutes",
            self._device_id,
            learned_dead_time,
        )
        self.hass.bus.async_fire(
            EVENT_DEAD_TIME_UPDATED,
            {
                "entry_id": self._device_id,
                "learned_dead_time": learned_dead_time,
            },
        )

    async def refresh_caches(self) -> None:
        """Refresh cached LHS value used by sensors.

        Called by sensors after an anticipation event to keep LHS in sync
        when the event publication bypasses the coordinator's async_update path.
        """
        if self._lhs_manager is None:
            return
        try:
            # Reload cached global LHS value
            self._lhs_cache = await self._lhs_manager.get_global_lhs()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to refresh LHS cache", exc_info=True)

    # Sensor accessors (synchronous for sensor entities)

    def get_learned_heating_slope(self) -> float:
        """Get cached global LHS for sensors."""
        return self._lhs_cache

    def get_contextual_learned_heating_slope(self, hour: int) -> float | None:
        """Get contextual LHS for a specific hour (from cache).

        This returns the contextual LHS from the synchronously-accessible cache.
        Falls back to global LHS if no contextual data is available for the hour.

        Args:
            hour: Hour of day (0-23)

        Returns:
            Contextual LHS for the hour, or global LHS as fallback
        """
        if hour < 0 or hour > 23:
            return self.get_learned_heating_slope()

        try:
            # Check contextual LHS cache first
            if hour in self._contextual_lhs_cache:
                contextual_value = self._contextual_lhs_cache[hour]
                # Return None only if truly no data (None in cache means no contextual data for this hour)
                if contextual_value is None:
                    return self.get_learned_heating_slope()  # Fallback to global
                return contextual_value

            # Not in cache, fallback to global LHS
            return self.get_learned_heating_slope()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to get LHS for hour %d", hour, exc_info=True)
            return self.get_learned_heating_slope()

    def is_ihp_enabled(self) -> bool:
        """Get IHP enabled state."""
        return self._ihp_enabled

    async def set_ihp_enabled(self, enabled: bool) -> None:
        """Set IHP enabled state.

        Args:
            enabled: True to enable IHP preheating, False to disable
        """
        _LOGGER.info("Setting IHP enabled state to: %s", enabled)
        self._ihp_enabled = enabled

        # Persist state to config entry if available
        if self._config_entry:
            new_options = dict(self._config_entry.options) if self._config_entry.options else {}
            new_options[CONF_IHP_ENABLED] = enabled
            self.hass.config_entries.async_update_entry(self._config_entry, options=new_options)

        # Trigger a recalculation to apply the new state
        await self.async_update()

    def get_vtherm_entity(self) -> str:
        """Get VTherm entity ID."""
        return self._vtherm_id

    def get_scheduler_entities(self) -> list[str]:
        """Get scheduler entity IDs."""
        return self._scheduler_ids[:]

    def is_auto_learning_enabled(self) -> bool:
        """Check if auto-learning is enabled.

        Returns:
            True if auto_learning is enabled in configuration
        """
        return self._auto_learning

    async def get_current_dead_time(self) -> float | None:
        """Get the current learned dead time value.

        Returns the dead time value persisted from auto-learning.

        Returns:
            Dead time in minutes, or None if not yet learned
        """
        _LOGGER.debug("Entering get_current_dead_time")

        if not self._lhs_storage:
            _LOGGER.debug("No LHS storage available")
            return None

        learned_dead_time = await self._lhs_storage.get_learned_dead_time()
        _LOGGER.debug("Exiting get_current_dead_time: result=%s", learned_dead_time)
        return learned_dead_time

    async def get_effective_dead_time(self) -> float:
        """Get the effective dead time for heating predictions.

        Returns either the auto-learned value or the user-configured value
        depending on the auto_learning configuration flag.

        Returns:
            Dead time in minutes (configured value or learned value)
        """
        _LOGGER.debug(
            "Entering get_effective_dead_time: auto_learning=%s, configured=%.1f",
            self._auto_learning,
            self._dead_time_minutes,
        )

        if self._auto_learning:
            # Use learned value if available, fall back to configured
            learned_dead_time = await self.get_current_dead_time()
            if learned_dead_time is not None:
                _LOGGER.debug(
                    "Exiting get_effective_dead_time: using learned value=%.1f",
                    learned_dead_time,
                )
                return learned_dead_time

        # Fall back to configured value (either auto_learning=False or no learned value yet)
        _LOGGER.debug(
            "Exiting get_effective_dead_time: using configured value=%.1f",
            self._dead_time_minutes,
        )
        return self._dead_time_minutes

    async def async_cleanup(self) -> None:
        """Cleanup coordinator resources.

        Cancels timers and stops cycle extraction.
        Called when coordinator is being unloaded.
        """
        _LOGGER.debug("Cleaning up coordinator: device_id=%s", self._device_config.device_id)

        try:
            # Stop cycle extraction and cancel timer
            if self._heating_cycle_manager:
                await self._heating_cycle_manager.cancel()
                _LOGGER.debug("Cycle extraction cancelled")

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Error during cleanup: %s", err, exc_info=True)
