"""The Intelligent Heating Pilot integration - DDD Architecture.

This module sets up the integration using a clean DDD architecture:
- Domain: Pure business logic (entities, value objects, services)
- Infrastructure: HA adapters (readers, commanders, event bridge)
- Application: Use case orchestration

The coordinator here is reduced to a thin setup/teardown manager.
"""

from __future__ import annotations

import hashlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .const import CONF_IHP_ENABLED, DOMAIN
from .heating_application import HeatingApplication
from .services import async_setup_services
from .utils.config_helpers import as_bool
from .view import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [Platform.SENSOR, Platform.SWITCH]

_STARTUP_UPDATE_BASE_DELAY_SECONDS = 5
_STARTUP_UPDATE_JITTER_SECONDS = 55
_STARTUP_EXTRACTION_BASE_DELAY_SECONDS = 120
_STARTUP_EXTRACTION_JITTER_SECONDS = 600
_LATE_UPDATE_BASE_DELAY_SECONDS = 30
_LATE_UPDATE_JITTER_SECONDS = 90


def _stable_jitter_seconds(seed: str, spread_seconds: int) -> int:
    """Return deterministic jitter in [0, spread_seconds] for a given seed."""
    if spread_seconds <= 0:
        return 0
    digest = hashlib.blake2s(seed.encode("utf-8"), digest_size=4).digest()
    value = int.from_bytes(digest, "big")
    return value % (spread_seconds + 1)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Intelligent Heating Pilot component."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize shared recorder access queue (FIFO) for all IHP devices.
    # This must be created before any device entry setup to ensure all adapters
    # share the same queue and recorder access is serialized across instances.
    from .infrastructure.recorder_queue import get_recorder_queue

    get_recorder_queue(hass)

    # Store hass in http app context for REST API views to access it
    hass.http.app["hass"] = hass

    # Register HTTP views once at the integration level (not per device)
    await async_register_http_views(hass)

    # Services belong to the integration, not to its first device (#192)
    async_setup_services(hass)

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
    coordinator._options_snapshot = dict(entry.options)
    await coordinator.async_load()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup event listeners
    coordinator.setup_listeners()

    def _schedule_startup_work() -> None:
        """Schedule startup work with deterministic per-entry staggering.

        This avoids synchronized bursts when many IHP entries start together.
        """
        extraction_delay = _STARTUP_EXTRACTION_BASE_DELAY_SECONDS + _stable_jitter_seconds(
            f"{entry.entry_id}:extract", _STARTUP_EXTRACTION_JITTER_SECONDS
        )
        update_delay = _STARTUP_UPDATE_BASE_DELAY_SECONDS + _stable_jitter_seconds(
            f"{entry.entry_id}:update", _STARTUP_UPDATE_JITTER_SECONDS
        )
        # Timed from HA start too: timed from setup, a slow startup could outlast it and
        # the update would be dropped, since updates do nothing until HA has started.
        late_update_delay = _LATE_UPDATE_BASE_DELAY_SECONDS + _stable_jitter_seconds(
            f"{entry.entry_id}:late_update", _LATE_UPDATE_JITTER_SECONDS
        )

        @callback
        def _run_extraction(_now):
            hass.async_create_task(coordinator.async_initialize_cycle_extraction())

        @callback
        def _run_update(_now):
            coordinator.request_startup_publish()

        @callback
        def _run_late_update(_now):
            _LOGGER.debug("[%s] Late update for late attribute population", entry.entry_id)
            hass.async_create_task(coordinator.async_update())

        entry.async_on_unload(
            async_track_point_in_time(
                hass,
                _run_update,
                dt_util.now() + dt_util.dt.timedelta(seconds=update_delay),
            )
        )
        entry.async_on_unload(
            async_track_point_in_time(
                hass,
                _run_late_update,
                dt_util.now() + dt_util.dt.timedelta(seconds=late_update_delay),
            )
        )
        entry.async_on_unload(
            async_track_point_in_time(
                hass,
                _run_extraction,
                dt_util.now() + dt_util.dt.timedelta(seconds=extraction_delay),
            )
        )

        _LOGGER.info(
            "[%s] Startup workload staggered: update in %ss, late update in %ss, "
            "extraction in %ss",
            entry.entry_id,
            update_delay,
            late_update_delay,
            extraction_delay,
        )

    @callback
    def _ha_started(_hass: HomeAssistant) -> None:
        _LOGGER.info(
            "[%s] HA started, initializing cycle extraction and triggering updates", entry.entry_id
        )
        _schedule_startup_work()

    # Wait for HA to have started before the cycle extraction and first update, so that
    # entities are available. If it already has, this runs straight away: the work is
    # still scheduled, not awaited, to avoid blocking the config flow (HA watchdog restart).
    # An is_running check would not do: it is also true while HA is starting, and the
    # staggered update would then be dropped with no retry. The listener is cancelled if
    # the entry unloads first, so a reloaded or removed device schedules no work for its
    # old coordinator (#192).
    entry.async_on_unload(async_at_started(hass, _ha_started))

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    The platforms are unloaded first: if that fails, the entry stays loaded and keeps a
    working coordinator instead of sensors bound to a cleaned-up one (#192).
    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator:
        await coordinator.async_cleanup()

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options and reload integration."""
    coordinator: HeatingApplication | None = hass.data[DOMAIN].get(entry.entry_id)

    previous_options = (
        dict(getattr(coordinator, "_options_snapshot", {}) or {}) if coordinator else {}
    )
    previous_no_toggle = {k: v for k, v in previous_options.items() if k != CONF_IHP_ENABLED}
    current_no_toggle = {k: v for k, v in entry.options.items() if k != CONF_IHP_ENABLED}
    ihp_enabled = as_bool(entry.options.get(CONF_IHP_ENABLED), default=True)

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
