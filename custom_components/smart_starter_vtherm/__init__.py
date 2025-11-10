"""The Smart Starter VTherm integration."""
from __future__ import annotations

import logging
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .calculator import PreheatingCalculator
from .const import (
    ATTR_CURRENT_TEMP,
    ATTR_OUTDOOR_TEMP,
    ATTR_PREHEAT_DURATION,
    ATTR_START_TIME,
    ATTR_TARGET_TEMP,
    ATTR_TARGET_TIME,
    CONF_CURRENT_TEMP_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_TARGET_TEMP_ENTITY,
    CONF_THERMAL_SLOPE,
    DEFAULT_THERMAL_SLOPE,
    DOMAIN,
    SERVICE_CALCULATE_START_TIME,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Service schema for calculate_start_time
SERVICE_CALCULATE_START_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("current_temp"): cv.positive_float,
        vol.Required("target_temp"): cv.positive_float,
        vol.Required("outdoor_temp"): vol.Coerce(float),
        vol.Required("target_time"): cv.datetime,
        vol.Optional("thermal_slope", default=DEFAULT_THERMAL_SLOPE): cv.positive_float,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Smart Starter VTherm component."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_calculate_start_time(call: ServiceCall) -> None:
        """Handle the calculate_start_time service call."""
        current_temp = call.data["current_temp"]
        target_temp = call.data["target_temp"]
        outdoor_temp = call.data["outdoor_temp"]
        target_time = call.data["target_time"]
        thermal_slope = call.data.get("thermal_slope", DEFAULT_THERMAL_SLOPE)

        _LOGGER.debug(
            "Service call: current=%.1f°C, target=%.1f°C, outdoor=%.1f°C, "
            "target_time=%s, slope=%.2f",
            current_temp,
            target_temp,
            outdoor_temp,
            target_time,
            thermal_slope,
        )

        calculator = PreheatingCalculator(thermal_slope=thermal_slope)
        result = calculator.calculate_start_time(
            current_temp=current_temp,
            target_temp=target_temp,
            outdoor_temp=outdoor_temp,
            target_time=target_time,
        )

        # Store result in hass.data for retrieval by sensors or automations
        hass.data[DOMAIN]["last_calculation"] = result

        _LOGGER.info(
            "Calculation result: Start at %s (in %.1f minutes)",
            result["start_time"].isoformat(),
            result["preheat_duration_minutes"],
        )

        # Fire an event with the result
        hass.bus.async_fire(
            f"{DOMAIN}_calculation_complete",
            {
                ATTR_START_TIME: result["start_time"].isoformat(),
                ATTR_PREHEAT_DURATION: result["preheat_duration_minutes"],
                ATTR_CURRENT_TEMP: result["current_temp"],
                ATTR_TARGET_TEMP: result["target_temp"],
                ATTR_OUTDOOR_TEMP: result["outdoor_temp"],
                ATTR_TARGET_TIME: result["target_time"].isoformat(),
                "should_start_now": result["should_start_now"],
            },
        )

    # Register the service
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_START_TIME,
        handle_calculate_start_time,
        schema=SERVICE_CALCULATE_START_TIME_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Starter VTherm from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_THERMAL_SLOPE: entry.data.get(CONF_THERMAL_SLOPE, DEFAULT_THERMAL_SLOPE),
        CONF_CURRENT_TEMP_ENTITY: entry.data.get(CONF_CURRENT_TEMP_ENTITY),
        CONF_TARGET_TEMP_ENTITY: entry.data.get(CONF_TARGET_TEMP_ENTITY),
        CONF_OUTDOOR_TEMP_ENTITY: entry.data.get(CONF_OUTDOOR_TEMP_ENTITY),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
