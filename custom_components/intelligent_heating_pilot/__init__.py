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
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import CONF_IHP_ENABLED, DOMAIN, SERVICE_CALCULATE_ANTICIPATED_START_TIME
from .coordinator import IntelligentHeatingPilotCoordinator
from .utils.config_helpers import as_bool
from .view import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Intelligent Heating Pilot component."""
    hass.data.setdefault(DOMAIN, {})

    # Store hass in http app context for REST API views to access it
    hass.http.app["hass"] = hass

    # Register HTTP views once at the integration level (not per device)
    await async_register_http_views(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intelligent Heating Pilot from a config entry.

    REFACTORED: Now uses HADeviceConfigReader to extract configuration
    and injects DeviceConfig into the Coordinator instead of passing
    config_entry directly.

    Args:
        hass: Home Assistant instance
        entry: Config entry to set up

    Returns:
        True if setup succeeded
    """
    _LOGGER.debug("Setting up IHP config entry: %s", entry.entry_id)

    hass.data.setdefault(DOMAIN, {})

    # ============================================================================
    # REFACTORING: Create device config reader and extract configuration
    # ============================================================================
    # Instead of passing config_entry to the Coordinator, we:
    # 1. Create HADeviceConfigReader (infrastructure adapter)
    # 2. Read DeviceConfig from config_entry (data + options)
    # 3. Inject DeviceConfig into Coordinator (dependency injection)

    from .infrastructure.adapters.device_config_reader import HADeviceConfigReader

    # Create device configuration reader (infrastructure layer)
    device_config_reader = HADeviceConfigReader(hass, entry)

    # Read complete device configuration (applies "options override data" logic)
    try:
        device_config = await device_config_reader.get_device_config(entry.entry_id)
    except ValueError as err:
        _LOGGER.error("Failed to load device configuration: %s", err)
        return False

    _LOGGER.debug(
        "Loaded device configuration: vtherm=%s, schedulers=%d, ihp_enabled=%s",
        device_config.vtherm_entity_id,
        len(device_config.scheduler_entities),
        device_config.ihp_enabled,
    )

    # ============================================================================
    # Create and load coordinator with injected configuration
    # ============================================================================
    # NEW: Coordinator ONLY receives device_config (pure DDD)
    # config_entry is passed later via setup_config_entry_access for options updates

    coordinator = IntelligentHeatingPilotCoordinator(hass, device_config)
    coordinator.setup_config_entry_access(entry)
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
    from .const import CONF_DATA_RETENTION_DAYS

    coordinator: IntelligentHeatingPilotCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)

    previous_options = (
        dict(getattr(coordinator, "_options_snapshot", {}) or {}) if coordinator else {}
    )
    previous_no_toggle = {k: v for k, v in previous_options.items() if k != CONF_IHP_ENABLED}
    current_no_toggle = {k: v for k, v in entry.options.items() if k != CONF_IHP_ENABLED}
    ihp_enabled = as_bool(entry.options.get(CONF_IHP_ENABLED), default=True)

    # Check if only retention days changed (reconfiguration of cycle refresh)
    retention_only_changed = (
        coordinator is not None
        and previous_no_toggle != current_no_toggle
        and len(set(previous_no_toggle.keys()) ^ set(current_no_toggle.keys())) == 1
        and CONF_DATA_RETENTION_DAYS
        in (set(previous_no_toggle.keys()) ^ set(current_no_toggle.keys()))
    )

    if retention_only_changed:
        # Handle retention change without reload
        new_retention_days = int(entry.options.get(CONF_DATA_RETENTION_DAYS, 10))
        _LOGGER.info(
            "[%s] Data retention changed to %d days, updating cycle refresh",
            entry.entry_id,
            new_retention_days,
        )
        if coordinator:
            coordinator._options_snapshot = dict(entry.options)
            coordinator._ihp_enabled = ihp_enabled
            await coordinator.async_notify_retention_change(new_retention_days)
        return

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
