"""Coordinator for Intelligent Heating Pilot integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .application import HeatingApplicationService
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

    async def async_cleanup(self) -> None:
        """Cleanup resources."""
        if self._event_bridge:
            self._event_bridge.cleanup()

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
        """Get cached LHS for sensors."""
        return self._lhs_cache

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
