"""The Intelligent Heating Pilot integration - DDD Architecture.

This module sets up the integration using a clean DDD architecture:
- Domain: Pure business logic (entities, value objects, services)
- Infrastructure: HA adapters (readers, commanders, event bridge)
- Application: Use case orchestration

The coordinator here is reduced to a thin setup/teardown manager.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .application import HeatingApplicationService
from .const import (
    CONF_AUTO_LEARNING,
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_DATA_RETENTION_DAYS,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_IHP_ENABLED,
    CONF_LHS_RETENTION_DAYS,
    CONF_MAX_CYCLE_DURATION_MINUTES,
    CONF_MIN_CYCLE_DURATION_MINUTES,
    CONF_SCHEDULER_ENTITIES,
    CONF_TEMP_DELTA_THRESHOLD,
    CONF_VTHERM_ENTITY,
    DECISION_MODE_SIMPLE,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_TEMP_DELTA_THRESHOLD,
    DOMAIN,
    SERVICE_CALCULATE_ANTICIPATED_START_TIME,
)
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
from .view import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [Platform.SENSOR, Platform.SWITCH]
LHS_CACHE_TTL_HOURS = 24


class IntelligentHeatingPilotCoordinator:
    """Lightweight coordinator for DDD architecture.

    This coordinator:
    - Creates and wires adapters
    - Creates application service
    - Setups event bridge
    - Exposes data for sensors (via application service)

    NO business logic - pure dependency injection and lifecycle management.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            config_entry: Config entry for this integration instance
        """
        self.hass = hass
        self.config = config_entry
        # Keep a snapshot of options to detect toggle-only changes (avoid reloads)
        self._options_snapshot = dict(config_entry.options or {})

        # Extract configuration with options override support
        self._vtherm_entity = self._get_config_value(CONF_VTHERM_ENTITY)
        self._scheduler_entities = self._get_scheduler_entities()
        self._humidity_in = self._get_config_value(CONF_HUMIDITY_IN_ENTITY)
        self._humidity_out = self._get_config_value(CONF_HUMIDITY_OUT_ENTITY)
        self._cloud_cover = self._get_config_value(CONF_CLOUD_COVER_ENTITY)
        # Support both old and new config keys for backward compatibility
        data_retention = self._get_config_value(CONF_DATA_RETENTION_DAYS)
        if data_retention is None:
            data_retention = self._get_config_value(CONF_LHS_RETENTION_DAYS)
        if data_retention is None:
            data_retention = DEFAULT_DATA_RETENTION_DAYS
        self._data_retention_days = int(data_retention)
        self._decision_mode = DECISION_MODE_SIMPLE

        # Heating cycle detection parameters
        temp_delta = self._get_config_value(CONF_TEMP_DELTA_THRESHOLD)
        self._temp_delta_threshold = float(
            temp_delta if temp_delta is not None else DEFAULT_TEMP_DELTA_THRESHOLD
        )
        # 0 means disabled (no splitting)
        cycle_split = self._get_config_value(CONF_CYCLE_SPLIT_DURATION_MINUTES)
        self._cycle_split_duration_minutes = int(
            cycle_split if cycle_split is not None else DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
        )
        min_cycle = self._get_config_value(CONF_MIN_CYCLE_DURATION_MINUTES)
        self._min_cycle_duration_minutes = int(
            min_cycle if min_cycle is not None else DEFAULT_MIN_CYCLE_DURATION_MINUTES
        )
        max_cycle = self._get_config_value(CONF_MAX_CYCLE_DURATION_MINUTES)
        self._max_cycle_duration_minutes = int(
            max_cycle if max_cycle is not None else DEFAULT_MAX_CYCLE_DURATION_MINUTES
        )
        dead_time = self._get_config_value(CONF_DEAD_TIME_MINUTES)
        self._dead_time_minutes = float(
            dead_time if dead_time is not None else DEFAULT_DEAD_TIME_MINUTES
        )
        auto_learning_value = self._get_config_value(CONF_AUTO_LEARNING)
        self._auto_learning = bool(
            auto_learning_value if auto_learning_value is not None else DEFAULT_AUTO_LEARNING
        )

        # IHP enabled state (default to True for backward compatibility)
        ihp_enabled_value = self._get_config_value(CONF_IHP_ENABLED)
        self._ihp_enabled = self._as_bool(ihp_enabled_value, default=True)

        # Infrastructure adapters
        self._model_storage: HAModelStorage | None = None
        self._cycle_cache: HACycleCache | None = None
        self._scheduler_reader: HASchedulerReader | None = None
        self._scheduler_commander: HASchedulerCommander | None = None
        self._climate_commander: HAClimateCommander | None = None
        self._environment_reader: HAEnvironmentReader | None = None

        # Application service
        self._app_service: HeatingApplicationService | None = None

        # Event bridge
        self._event_bridge: HAEventBridge | None = None

        # Cached data for sensors (refreshed by application service)
        self._last_anticipation_data: dict[str, Any] | None = None
        self._lhs_cache: float = 2.0  # Default

    async def async_load(self) -> None:
        """Load and initialize all components."""
        # Create infrastructure adapters
        self._model_storage = HAModelStorage(
            self.hass, self.config.entry_id, retention_days=self._data_retention_days
        )

        # Create cycle cache for incremental cycle extraction
        self._cycle_cache = HACycleCache(
            self.hass, self.config.entry_id, retention_days=self._data_retention_days
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
            entry_id=self.config.entry_id,
            get_ihp_enabled_func=self.is_ihp_enabled,
        )

        # Load initial data
        self._lhs_cache = await self._model_storage.get_learned_heating_slope()

        _LOGGER.info(
            "[%s] Coordinator initialized (VTherm: %s, Schedulers: %d)",
            self.config.entry_id,
            self._vtherm_entity,
            len(self._scheduler_entities),
        )

        # NOTE: Initial update is now deferred to async_setup_entry to avoid blocking
        # the config flow during device creation (prevents HA watchdog restart).
        # See lines 368-394 for the deferred update logic.

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
                        "entry_id": self.config.entry_id,
                        "clear_values": True,
                    },
                )
            else:
                # Normal anticipation data
                self.hass.bus.async_fire(
                    f"{DOMAIN}_anticipation_calculated",
                    {
                        "entry_id": self.config.entry_id,
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

        # Update config entry options to persist state
        # Note: async_update_entry schedules an async update but returns None (fire-and-forget)
        # so it doesn't need to be awaited here
        new_options = dict(self.config.options) if self.config.options else {}
        new_options[CONF_IHP_ENABLED] = enabled

        # Update snapshot before and after so the options listener can short-circuit reloads
        self._options_snapshot = dict(self.config.options or {})
        self.hass.config_entries.async_update_entry(self.config, options=new_options)
        self._options_snapshot = dict(new_options)

        # Trigger a recalculation to apply the new state
        await self.async_update()

    def get_vtherm_entity(self) -> str:
        """Get VTherm entity ID."""
        return cast(str, self._vtherm_entity)

    def get_scheduler_entities(self) -> list[str]:
        """Get scheduler entity IDs."""
        return self._scheduler_entities[:]

    # Configuration helpers

    def _get_config_value(self, key: str) -> Any:
        """Get config value with options override support."""
        if isinstance(self.config.options, dict) and key in self.config.options:
            return self.config.options[key]
        return self.config.data.get(key)

    def _get_scheduler_entities(self) -> list[str]:
        """Get scheduler entities with robust type handling."""
        has_options = isinstance(self.config.options, dict) or hasattr(self.config.options, "get")
        options_schedulers = (
            self.config.options.get(CONF_SCHEDULER_ENTITIES) if has_options else None
        )

        if has_options and options_schedulers is not None:
            raw = options_schedulers
            if isinstance(raw, list):
                return [r for r in raw if isinstance(r, str) and r]
            if isinstance(raw, str):
                return [raw]
            return []

        raw = self.config.data.get(CONF_SCHEDULER_ENTITIES, [])
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, str) and r]
        if isinstance(raw, str):
            return [raw]
        return []

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        """Normalize truthy/falsy values to a strict boolean.

        Important for stringified options (e.g. "False" should yield False).
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    async def _get_global_lhs_cached_or_fallback(self) -> float:
        """Return global LHS from cache if fresh, otherwise fallback to stored value.

        Prefers the cached global LHS updated within the last 24 hours; if not
        available or stale, falls back to the persisted learned LHS.
        """
        if not self._model_storage:
            return self._lhs_cache

        try:
            cached = await self._model_storage.get_cached_global_lhs()
            if cached:
                age = dt_util.utcnow() - cached.updated_at
                if age <= dt_util.dt.timedelta(hours=LHS_CACHE_TTL_HOURS):
                    _LOGGER.info(
                        "[%s] Using cached global LHS (age %.1f h): %.2f°C/h",
                        self.config.entry_id,
                        age.total_seconds() / 3600,
                        cached.value,
                    )
                    return cached.value
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to read cached global LHS", exc_info=True)

        fallback = await self._model_storage.get_learned_heating_slope()
        _LOGGER.debug("[%s] Using fallback learned LHS: %.2f°C/h", self.config.entry_id, fallback)
        return fallback


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Intelligent Heating Pilot component."""
    hass.data.setdefault(DOMAIN, {})

    # Store hass in http app context for REST API views to access it
    hass.http.app["hass"] = hass

    # Register HTTP views once at the integration level (not per device)
    await async_register_http_views(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intelligent Heating Pilot from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create and load coordinator
    coordinator = IntelligentHeatingPilotCoordinator(hass, entry)
    await coordinator.async_load()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup event listeners
    coordinator.setup_listeners()

    # Wait for HA to be fully started before first update
    # This ensures all entities (especially scheduler entities) are available
    @callback
    def _ha_started(_event):
        _LOGGER.info("[%s] HA started, triggering initial update", entry.entry_id)
        hass.async_create_task(coordinator.async_update())

    # Schedule initial update asynchronously to avoid blocking config flow
    # This prevents HA watchdog restart during device creation with scheduler
    if hass.is_running:
        _LOGGER.debug(
            "[%s] HA already running, scheduling non-blocking async update", entry.entry_id
        )
        hass.async_create_task(coordinator.async_update())
    else:
        _LOGGER.debug("[%s] Waiting for HA start event before first update", entry.entry_id)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _ha_started)

    # Small delayed update for late attribute population
    @callback
    def _delayed_update(_now):
        _LOGGER.debug("[%s] Delayed update", entry.entry_id)
        hass.async_create_task(coordinator.async_update())

    async_track_point_in_time(
        hass,
        _delayed_update,
        dt_util.now() + dt_util.dt.timedelta(seconds=30),
    )

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register services
    async def handle_reset_learning(call):
        """Handle reset_learning service."""
        if coordinator._app_service:
            await coordinator._app_service.reset_learned_slopes()
            # Refresh LHS cache
            if coordinator._model_storage:
                coordinator._lhs_cache = (
                    await coordinator._model_storage.get_learned_heating_slope()
                )

    async def handle_calculate_anticipated_start_time(call: ServiceCall):
        """Handle calculate_anticipated_start_time service.

        This service calculates the anticipated start time for a given IHP device
        to reach a target temperature at a specified time. It uses the device's
        learned heating slope and current environmental data.
        """
        _LOGGER.debug("Entering handle_calculate_anticipated_start_time")

        # Extract service call parameters
        entity_id = call.data.get("entity_id")
        target_time_raw = call.data.get("target_time")
        target_temp = call.data.get("target_temp")

        if not entity_id:
            _LOGGER.error("entity_id is required for calculate_anticipated_start_time service")
            return

        if not target_time_raw:
            _LOGGER.error("target_time is required for calculate_anticipated_start_time service")
            return

        # Parse target_time
        if isinstance(target_time_raw, str):
            target_time = dt_util.parse_datetime(target_time_raw)
            if target_time is None:
                try:
                    target_time = datetime.fromisoformat(target_time_raw)
                except ValueError:
                    _LOGGER.error("Invalid target_time format: %s", target_time_raw)
                    return
        elif isinstance(target_time_raw, datetime):
            target_time = target_time_raw
        else:
            _LOGGER.error("Invalid target_time type: %s", type(target_time_raw))
            return

        # Ensure target_time has timezone
        if target_time.tzinfo is None:
            target_time = dt_util.as_local(target_time)

        # Extract entry_id from entity_id
        # Entity IDs follow pattern: sensor.{name}_{sensor_type}
        # We need to find the config entry that owns this entity
        entry_id_found = None
        for entry_id, coord in hass.data[DOMAIN].items():
            if isinstance(coord, IntelligentHeatingPilotCoordinator):
                # Check if this coordinator owns the entity by checking entity registry
                entity_reg = er.async_get(hass)
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.config_entry_id == entry_id:
                    entry_id_found = entry_id
                    break

        if not entry_id_found:
            _LOGGER.error("Could not find IHP device for entity_id: %s", entity_id)
            return

        # Get the coordinator for this device
        device_coordinator = hass.data[DOMAIN].get(entry_id_found)
        if not device_coordinator or not isinstance(
            device_coordinator, IntelligentHeatingPilotCoordinator
        ):
            _LOGGER.error("Invalid coordinator for entry_id: %s", entry_id_found)
            return

        # Get current environment
        if not device_coordinator._environment_reader:
            _LOGGER.error("Environment reader not available for device")
            return

        environment = await device_coordinator._environment_reader.get_current_environment()
        if not environment:
            _LOGGER.error("Could not read current environment")
            return

        # Use target_temp from service call, or fallback to VTherm's current target
        if target_temp is None:
            # Try to get target temp from VTherm
            vtherm_state = hass.states.get(device_coordinator._vtherm_entity)
            if vtherm_state:
                target_temp = vtherm_state.attributes.get("temperature")
            if target_temp is None:
                _LOGGER.error("target_temp not provided and could not be read from VTherm")
                return

        target_temp = float(target_temp)

        # Get learned heating slope (contextual)
        if not device_coordinator._app_service:
            _LOGGER.error("Application service not available for device")
            return

        lhs = await device_coordinator._app_service._get_contextual_lhs(target_time)

        # Calculate anticipated start time using prediction service
        from .domain.services import PredictionService

        prediction_service = PredictionService()

        prediction = prediction_service.predict_heating_time(
            current_temp=environment.indoor_temperature,
            target_temp=target_temp,
            outdoor_temp=environment.outdoor_temp,
            humidity=environment.indoor_humidity,
            learned_slope=lhs,
            target_time=target_time,
            cloud_coverage=environment.cloud_coverage,
        )

        _LOGGER.info(
            "Service calculate_anticipated_start_time: "
            "anticipated_start=%s, target_time=%s, target_temp=%.1f°C, "
            "current_temp=%.1f°C, LHS=%.2f°C/h, confidence=%.2f",
            prediction.anticipated_start_time.isoformat(),
            target_time.isoformat(),
            target_temp,
            environment.indoor_temperature,
            prediction.learned_heating_slope,
            prediction.confidence_level,
        )

        # Return the result as service response data
        # Note: Service responses are only available in HA 2023.7+
        # For older versions, this will just log the result
        return {
            "anticipated_start_time": prediction.anticipated_start_time.isoformat(),
            "target_time": target_time.isoformat(),
            "target_temp": target_temp,
            "current_temp": environment.indoor_temperature,
            "estimated_duration_minutes": prediction.estimated_duration_minutes,
            "learned_heating_slope": prediction.learned_heating_slope,
            "confidence_level": prediction.confidence_level,
        }

    # Define service schema
    calculate_anticipated_start_time_schema = vol.Schema(
        {
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("target_time"): cv.datetime,
            vol.Optional("target_temp"): vol.Coerce(float),
        }
    )

    hass.services.async_register(DOMAIN, "reset_learning", handle_reset_learning)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_ANTICIPATED_START_TIME,
        handle_calculate_anticipated_start_time,
        schema=calculate_anticipated_start_time_schema,
        supports_response=SupportsResponse.ONLY,
    )

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_cleanup()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return cast(bool, unload_ok)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options and reload integration."""
    coordinator: IntelligentHeatingPilotCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)

    previous_options = (
        dict(getattr(coordinator, "_options_snapshot", {}) or {}) if coordinator else {}
    )
    previous_no_toggle = {k: v for k, v in previous_options.items() if k != CONF_IHP_ENABLED}
    current_no_toggle = {k: v for k, v in entry.options.items() if k != CONF_IHP_ENABLED}
    ihp_enabled = IntelligentHeatingPilotCoordinator._as_bool(
        entry.options.get(CONF_IHP_ENABLED),
        default=True,
    )

    # If only the ihp_enabled flag changed, skip full reload
    if coordinator and previous_no_toggle == current_no_toggle:
        _LOGGER.info("[%s] Options updated (ihp_enabled only), skipping reload", entry.entry_id)
        coordinator._options_snapshot = dict(entry.options)
        coordinator._ihp_enabled = ihp_enabled
        await coordinator.async_update()
        return

    _LOGGER.info("[%s] Options updated, reloading", entry.entry_id)
    if coordinator:
        coordinator._options_snapshot = dict(entry.options)

    await hass.config_entries.async_reload(entry.entry_id)

    # Schedule async update after reload (non-blocking)
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        hass.async_create_task(coordinator.async_update())
