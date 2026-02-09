"""Coordinator for Intelligent Heating Pilot integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .application import HeatingApplicationService
from .application.extract_heating_cycles_factory import ExtractHeatingCyclesUseCaseFactory
from .application.extract_heating_cycles_use_case import ExtractHeatingCyclesUseCase
from .const import CONF_IHP_ENABLED, DECISION_MODE_SIMPLE, DOMAIN
from .domain.interfaces.device_config_reader_interface import DeviceConfig
from .infrastructure.adapters import (
    HAClimateCommander,
    HACycleCache,
    HAEnvironmentReader,
    HAModelStorage,
    HASchedulerCommander,
    HASchedulerReader,
    HATimerScheduler,
)
from .infrastructure.event_bridge import HAEventBridge

_LOGGER = logging.getLogger(__name__)


class IntelligentHeatingPilotCoordinator:
    """Lightweight coordinator for DDD architecture.

    This coordinator:
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
        _LOGGER.debug("Initializing IntelligentHeatingPilotCoordinator with injected DeviceConfig")

        self.hass = hass
        self._entry_id = device_config.device_id  # Store entry ID for adapter creation

        # Store immutable device configuration
        self._device_config = device_config

        # Extract configuration from DeviceConfig (NOT from config_entry!)
        # This is the key change: we read from the injected value object
        self._vtherm_entity = device_config.vtherm_entity_id
        self._scheduler_entities = device_config.scheduler_entities
        self._humidity_in = device_config.humidity_in_entity_id
        self._humidity_out = device_config.humidity_out_entity_id
        self._cloud_cover = device_config.cloud_cover_entity_id
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
        self._model_storage: HAModelStorage | None = None
        self._cycle_cache: HACycleCache | None = None
        self._scheduler_reader: HASchedulerReader | None = None
        self._scheduler_commander: HASchedulerCommander | None = None
        self._climate_commander: HAClimateCommander | None = None
        self._environment_reader: HAEnvironmentReader | None = None
        self._timer_scheduler: HATimerScheduler | None = None

        # Application service
        self._app_service: HeatingApplicationService | None = None

        # Cycle extraction use case (lifecycle management)
        self._extract_cycles_use_case: ExtractHeatingCyclesUseCase | None = None

        # Event bridge
        self._event_bridge: HAEventBridge | None = None

        # Cached data for sensors (refreshed by application service)
        self._last_anticipation_data: dict[str, Any] | None = None
        self._lhs_cache: float = 2.0  # Default

        # Config entry for options updates (set later via setup_config_entry_access)
        self._config_entry: ConfigEntry | None = None
        self._options_snapshot: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load and initialize all components."""
        # Create infrastructure adapters
        self._model_storage = HAModelStorage(
            self.hass, self._entry_id, retention_days=self._data_retention_days
        )

        # Create cycle cache for incremental cycle extraction
        self._cycle_cache = HACycleCache(
            self.hass, self._entry_id, retention_days=self._data_retention_days
        )

        self._scheduler_reader = HASchedulerReader(
            self.hass,
            self._scheduler_entities,
            vtherm_entity_id=self._vtherm_entity,
        )

        self._scheduler_commander = HASchedulerCommander(self.hass)

        self._climate_commander = HAClimateCommander(self.hass, self._vtherm_entity)
        self._environment_reader = HAEnvironmentReader(
            self.hass,
            self._vtherm_entity,
            outdoor_temp_entity_id=None,  # TODO: Add to config
            humidity_in_entity_id=self._humidity_in,
            humidity_out_entity_id=self._humidity_out,
            cloud_cover_entity_id=self._cloud_cover,
        )

        # Create timer scheduler adapter
        self._timer_scheduler = HATimerScheduler(self.hass)

        # Create application service
        self._app_service = HeatingApplicationService(
            scheduler_reader=self._scheduler_reader,
            model_storage=self._model_storage,
            scheduler_commander=self._scheduler_commander,
            climate_commander=self._climate_commander,
            environment_reader=self._environment_reader,
            timer_scheduler=self._timer_scheduler,
            cycle_cache=self._cycle_cache,
            history_lookback_days=self._data_retention_days,
            decision_mode=self._decision_mode,
            temp_delta_threshold=self._temp_delta_threshold,
            cycle_split_duration_minutes=self._cycle_split_duration_minutes,
            min_cycle_duration_minutes=self._min_cycle_duration_minutes,
            max_cycle_duration_minutes=self._max_cycle_duration_minutes,
            dead_time_minutes=self._dead_time_minutes,
            auto_learning=self._auto_learning,
        )

        # Create event bridge
        monitored_entities = []
        if self._humidity_in:
            monitored_entities.append(self._humidity_in)
        if self._humidity_out:
            monitored_entities.append(self._humidity_out)
        if self._cloud_cover:
            monitored_entities.append(self._cloud_cover)

        self._event_bridge = HAEventBridge(
            self.hass,
            self._app_service,
            self._vtherm_entity,
            self._scheduler_entities,
            monitored_entities,
            entry_id=self._entry_id,
            get_ihp_enabled_func=self.is_ihp_enabled,
        )

        # Load initial data
        self._lhs_cache = await self._model_storage.get_learned_heating_slope()

        # Initialize cycle refresh (extraction + 24h periodic)
        if self._data_retention_days > 0:
            await self._initialize_cycle_refresh()
        else:
            _LOGGER.debug(
                "Cycle extraction disabled (history_lookback_days=%d)",
                self._data_retention_days,
            )

        _LOGGER.info(
            "[%s] Coordinator initialized (VTherm: %s, Schedulers: %d)",
            self._entry_id,
            self._vtherm_entity,
            len(self._scheduler_entities),
        )

        # NOTE: Initial update is now deferred to async_setup_entry to avoid blocking
        # the config flow during device creation (prevents HA watchdog restart).
        # See async_setup_entry for the deferred update logic.

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

    async def _initialize_cycle_refresh(self) -> None:
        """Initialize cycle extraction and schedule 24h periodic refresh.

        This method:
        - Creates ExtractHeatingCyclesUseCase via factory
        - Performs initial extraction over retention window
        - Schedules 24h periodic refresh timer
        - Logs initialization with retention days
        """
        _LOGGER.debug("Entering _initialize_cycle_refresh for device=%s", self._entry_id)

        try:
            # Sanity checks
            if not self._device_config:
                _LOGGER.warning("Cannot initialize cycle refresh: device_config not available")
                return

            if not self._app_service:
                _LOGGER.warning(
                    "Cannot initialize cycle refresh: application service not available"
                )
                return

            # Create use case via factory (wires all dependencies including adapters)
            self._extract_cycles_use_case = ExtractHeatingCyclesUseCaseFactory.create(
                hass=self.hass,
                app_service=self._app_service,
                device_config=self._device_config,
                cycle_cache=self._cycle_cache,
                timer_scheduler=self._timer_scheduler,
                model_storage=self._model_storage,
            )

            _LOGGER.debug(
                "ExtractHeatingCyclesUseCase created via factory for device=%s",
                self._entry_id,
            )

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
            extracted_cycles = await self._extract_cycles_use_case.execute(
                device_id=self._device_config.device_id,
                start_time=start_time,
                end_time=now,
            )

            # Update global LHS from extracted cycles (if any)
            if extracted_cycles and self._app_service:
                await self._update_global_lhs_from_cycles(extracted_cycles)

            _LOGGER.info(
                "Cycle extraction initialized: device=%s, retention=%d days, cycles=%d",
                self._device_config.device_id,
                self._data_retention_days,
                len(extracted_cycles),
            )

            _LOGGER.debug("Exiting _initialize_cycle_refresh for device=%s", self._entry_id)

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to initialize cycle extraction: %s", err, exc_info=True)

    async def _update_global_lhs_from_cycles(self, cycles: list) -> None:
        """Update global LHS in model storage from extracted cycles.

        This method calculates the global learned heating slope (LHS) from
        all extracted cycles and persists it to model storage for later use
        as a fallback when no contextual data is available.

        Args:
            cycles: List of HeatingCycle objects
        """
        if not cycles or not self._app_service or not self._model_storage:
            return

        try:
            # Get LHS calculation service from application service
            lhs_service = self._app_service._lhs_calculation_service

            # Calculate global LHS from all cycles
            global_lhs = lhs_service.calculate_global_lhs(cycles)

            # Persist to storage with current timestamp
            now = dt_util.utcnow()
            await self._model_storage.set_cached_global_lhs(global_lhs, now)

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
            if self._extract_cycles_use_case:
                await self._extract_cycles_use_case.on_retention_changed(new_retention_days)
            else:
                _LOGGER.debug("No active use case; cannot propagate retention change")

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Error handling retention change: %s", err, exc_info=True)

    async def async_update(self) -> None:
        """Trigger anticipation calculation and cache results for sensors."""
        if not self._app_service:
            return

        # Calculate and schedule via application service (passing IHP enabled state)
        anticipation_data = await self._app_service.calculate_and_schedule_anticipation(
            ihp_enabled=self._ihp_enabled
        )

        # Cache for sensors
        self._last_anticipation_data = anticipation_data

        # Refresh LHS cache
        if self._model_storage:
            self._lhs_cache = await self._model_storage.get_learned_heating_slope()

        # Fire event for sensors
        if anticipation_data:
            # Check if this is a "clear values" event (no scheduler configured)
            if anticipation_data.get("clear_values"):
                _LOGGER.debug("No scheduler configured - firing clear_values event for sensors")
                self.hass.bus.async_fire(
                    f"{DOMAIN}_anticipation_calculated",
                    {
                        "entry_id": self._entry_id,
                        "clear_values": True,
                    },
                )
            else:
                # Normal anticipation data
                self.hass.bus.async_fire(
                    f"{DOMAIN}_anticipation_calculated",
                    {
                        "entry_id": self._entry_id,
                        "anticipated_start_time": anticipation_data[
                            "anticipated_start_time"
                        ].isoformat(),
                        "next_schedule_time": anticipation_data["next_schedule_time"].isoformat(),
                        "next_target_temperature": anticipation_data["next_target_temperature"],
                        "anticipation_minutes": anticipation_data["anticipation_minutes"],
                        "current_temp": anticipation_data["current_temp"],
                        "learned_heating_slope": anticipation_data["learned_heating_slope"],
                        "confidence_level": anticipation_data["confidence_level"],
                        "scheduler_entity": anticipation_data.get("scheduler_entity", ""),
                    },
                )

    async def refresh_caches(self) -> None:
        """Refresh cached LHS value used by sensors.

        Called by sensors after an anticipation event to keep LHS in sync
        when the event publication bypasses the coordinator's async_update path.
        """
        if self._model_storage is None:
            return
        try:
            self._lhs_cache = await self._model_storage.get_learned_heating_slope()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to refresh LHS cache", exc_info=True)

    # Sensor accessors (synchronous for sensor entities)

    def get_learned_heating_slope(self) -> float:
        """Get cached global LHS for sensors."""
        return self._lhs_cache

    def get_contextual_learned_heating_slope(self, hour: int) -> float | None:
        """Get contextual LHS for a specific hour (synchronous fallback).

        Since _get_contextual_lhs is async and sensors need sync accessors,
        this returns the global LHS as fallback. In production, this should be
        enhanced with a cached contextual LHS lookup.

        Args:
            hour: Hour of day (0-23)

        Returns:
            Global LHS (contextual not available synchronously)
        """
        try:
            # For now, return global LHS as fallback
            # In future: implement LHS_BY_HOUR cache for proper contextual values
            return self.get_learned_heating_slope()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to get LHS for hour %d", hour, exc_info=True)
            return None

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
        return self._vtherm_entity

    def get_scheduler_entities(self) -> list[str]:
        """Get scheduler entity IDs."""
        return self._scheduler_entities[:]

    async def async_cleanup(self) -> None:
        """Cleanup coordinator resources.

        Cancels timers and stops cycle extraction.
        Called when coordinator is being unloaded.
        """
        _LOGGER.debug("Cleaning up coordinator: device_id=%s", self._device_config.device_id)

        try:
            # Stop cycle extraction and cancel timer
            if self._extract_cycles_use_case:
                await self._extract_cycles_use_case.cancel()
                _LOGGER.debug("Cycle extraction cancelled")

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Error during cleanup: %s", err, exc_info=True)
