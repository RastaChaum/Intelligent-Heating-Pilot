"""The Intelligent Heating Pilot integration - DDD Architecture.

This module sets up the integration using a clean DDD architecture:
- Domain: Pure business logic (entities, value objects, services)
- Infrastructure: HA adapters (readers, commanders, event bridge)
- Application: Use case orchestration

The coordinator here is reduced to a thin setup/teardown manager.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import CONF_IHP_ENABLED, DOMAIN, SERVICE_CALCULATE_ANTICIPATED_START_TIME
from .heating_application import HeatingApplication
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

    coordinator = HeatingApplication(hass, device_config)
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
        """Handle reset_learning service.

        Delegates to orchestrator - no business logic here.
        """
        await coordinator._orchestrator.reset_all_learning_data()

    async def handle_calculate_anticipated_start_time(call: ServiceCall):
        """Handle calculate_anticipated_start_time service.

        This service calculates the anticipated start time for a given IHP device
        to reach a target temperature at a specified time.

        Delegates to orchestrator's calculate_anticipation_only() - no business logic here.
        """
        _LOGGER.debug("Entering handle_calculate_anticipated_start_time")

        # Extract service call parameters
        entity_id = call.data["entity_id"]
        target_time = call.data["target_time"]
        target_temp = call.data.get("target_temp")

        # Ensure target_time has timezone
        if target_time.tzinfo is None:
            target_time = dt_util.as_local(target_time)

        # Extract entry_id from entity_id
        # Entity IDs follow pattern: sensor.{name}_{sensor_type}
        # We need to find the config entry that owns this entity
        entry_id_found = None
        for entry_id, coord in hass.data[DOMAIN].items():
            if isinstance(coord, HeatingApplication):
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
        if not device_coordinator or not isinstance(device_coordinator, HeatingApplication):
            _LOGGER.error("Invalid coordinator for entry_id: %s", entry_id_found)
            return

        # Get target_temp from service call or VTherm
        if target_temp is None:
            # Try to get target temp from VTherm
            vtherm_state = hass.states.get(device_coordinator._vtherm_id)
            if vtherm_state:
                target_temp = vtherm_state.attributes.get("temperature")
        if target_temp is not None:
            target_temp = float(target_temp)

        # Delegate to orchestrator (pure routing - no business logic)
        anticipation_data = await device_coordinator._orchestrator.calculate_anticipation_only(
            target_time=target_time,
            target_temp=target_temp,
        )

        # Extract fields from anticipation_data (which is already structured)
        anticipated_start_time = anticipation_data.get("anticipated_start_time")
        response_target_time = anticipation_data.get("next_schedule_time") or target_time
        response_target_temp = anticipation_data.get("next_target_temperature")
        if response_target_temp is None:
            response_target_temp = target_temp
        if anticipated_start_time is None:
            _LOGGER.warning("Could not calculate anticipated start time (insufficient data)")
            # Return structure with None values
            return {
                "anticipated_start_time": None,
                "target_time": response_target_time.isoformat(),
                "target_temp": response_target_temp,
                "current_temp": anticipation_data.get("current_temp"),
                "estimated_duration_minutes": None,
                "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
                "confidence_level": None,
            }

        _LOGGER.info(
            "Service calculate_anticipated_start_time: "
            "anticipated_start=%s, target_time=%s, target_temp=%.1f°C, "
            "current_temp=%.1f°C, LHS=%.2f°C/h, confidence=%.2f",
            anticipated_start_time.isoformat(),
            response_target_time.isoformat(),
            response_target_temp or 0.0,
            anticipation_data.get("current_temp") or 0.0,
            anticipation_data.get("learned_heating_slope") or 0.0,
            anticipation_data.get("confidence_level") or 0.0,
        )

        # Return the result as service response data
        return {
            "anticipated_start_time": anticipated_start_time.isoformat(),
            "target_time": response_target_time.isoformat(),
            "target_temp": response_target_temp,
            "current_temp": anticipation_data.get("current_temp"),
            "estimated_duration_minutes": anticipation_data.get("estimated_duration_minutes"),
            "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
            "confidence_level": anticipation_data.get("confidence_level"),
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

    return bool(unload_ok)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options and reload integration."""
    from .const import CONF_DATA_RETENTION_DAYS

    coordinator: HeatingApplication | None = hass.data[DOMAIN].get(entry.entry_id)

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
