"""The Intelligent Heating Pilot integration - DDD Architecture.

This module sets up the integration using a clean DDD architecture:
- Domain: Pure business logic (entities, value objects, services)
- Infrastructure: HA adapters (readers, commanders, event bridge)
- Application: Use case orchestration

The coordinator here is reduced to a thin setup/teardown manager.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .application import HeatingApplicationService
from .const import (
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DECISION_MODE_SIMPLE,
    DEFAULT_LHS_RETENTION_DAYS,
    DOMAIN,
)
from .infrastructure.adapters import (
    HAClimateCommander,
    HAEnvironmentReader,
    HAModelStorage,
    HASchedulerCommander,
    HASchedulerReader,
)
from .infrastructure.event_bridge import HAEventBridge
from .view import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [Platform.SENSOR]
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
        
        # Extract configuration with options override support
        self._vtherm_entity = self._get_config_value(CONF_VTHERM_ENTITY)
        self._scheduler_entities = self._get_scheduler_entities()
        self._humidity_in = self._get_config_value(CONF_HUMIDITY_IN_ENTITY)
        self._humidity_out = self._get_config_value(CONF_HUMIDITY_OUT_ENTITY)
        self._cloud_cover = self._get_config_value(CONF_CLOUD_COVER_ENTITY)
        self._lhs_retention_days = int(self._get_config_value(CONF_LHS_RETENTION_DAYS) or DEFAULT_LHS_RETENTION_DAYS)
        self._decision_mode = DECISION_MODE_SIMPLE
        
        # Infrastructure adapters
        self._model_storage: HAModelStorage | None = None
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
            self.hass,
            self.config.entry_id,
            retention_days=self._lhs_retention_days
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
        
        # Create application service
        self._app_service = HeatingApplicationService(
            scheduler_reader=self._scheduler_reader,
            model_storage=self._model_storage,
            scheduler_commander=self._scheduler_commander,
            climate_commander=self._climate_commander,
            environment_reader=self._environment_reader,
            history_lookback_days=self._lhs_retention_days,
            decision_mode=self._decision_mode,
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
        )
        
        # Load initial data
        self._lhs_cache = await self._get_global_lhs_cached_or_fallback()
        
        _LOGGER.info(
            "[%s] Coordinator initialized (VTherm: %s, Schedulers: %d)",
            self.config.entry_id,
            self._vtherm_entity,
            len(self._scheduler_entities),
        )
        
        # Trigger initial calculation for sensors
        await self.async_update()
    
    def setup_listeners(self) -> None:
        """Setup event listeners via event bridge."""
        if self._event_bridge:
            self._event_bridge.setup_listeners()
    
    async def async_update(self) -> None:
        """Trigger anticipation calculation and cache results for sensors."""
        if not self._app_service:
            return
        
        # Calculate and schedule via application service
        anticipation_data = await self._app_service.calculate_and_schedule_anticipation()
        
        # Cache for sensors
        self._last_anticipation_data = anticipation_data
        
        # Refresh LHS cache
        if self._model_storage:
            self._lhs_cache = await self._get_global_lhs_cached_or_fallback()
        
        # Fire event for sensors
        if anticipation_data:
            self.hass.bus.async_fire(
                f"{DOMAIN}_anticipation_calculated",
                {
                    "entry_id": self.config.entry_id,
                    "anticipated_start_time": anticipation_data["anticipated_start_time"].isoformat(),
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
            self._lhs_cache = await self._get_global_lhs_cached_or_fallback()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to refresh LHS cache", exc_info=True)
    
    # Sensor accessors (synchronous for sensor entities)
    
    def get_learned_heating_slope(self) -> float:
        """Get cached LHS for sensors."""
        return self._lhs_cache
    

    
    def get_vtherm_entity(self) -> str:
        """Get VTherm entity ID."""
        return self._vtherm_entity
    
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
        options_schedulers = self.config.options.get(CONF_SCHEDULER_ENTITIES) if has_options else None
        
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
    
    # If HA already started, trigger update immediately, otherwise wait
    if hass.is_running:
        _LOGGER.debug("[%s] HA already running, triggering update now", entry.entry_id)
        await coordinator.async_update()
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
                coordinator._lhs_cache = await coordinator._model_storage.get_learned_heating_slope()
    
    hass.services.async_register(DOMAIN, "reset_learning", handle_reset_learning)
    
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
    
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options and reload integration."""
    _LOGGER.info("[%s] Options updated, reloading", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
    
    # Force update after reload
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_update()
