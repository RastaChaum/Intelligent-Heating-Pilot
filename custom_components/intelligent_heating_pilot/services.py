"""Service actions of the Intelligent Heating Pilot integration.

The services are registered once, when the integration is set up, and stay registered for its
whole lifetime, as the Home Assistant integration quality scale requires (rule
``action-setup``). Automations calling them therefore validate even when no device is loaded;
a call that targets no loaded device raises ``ServiceValidationError`` (#192).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .application.use_cases import LearningResetError
from .const import DOMAIN, SERVICE_CALCULATE_ANTICIPATED_START_TIME
from .heating_application import HeatingApplication

_LOGGER = logging.getLogger(__name__)

SERVICE_RESET_LEARNING = "reset_learning"

# Home Assistant 2026.3+ aliases voluptuous to probatio at runtime, but its type
# hints name probatio: voluptuous schemas still work, only mypy disagrees.
RESET_LEARNING_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id})

CALCULATE_ANTICIPATED_START_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("target_time"): cv.datetime,
        vol.Optional("target_temp"): vol.Coerce(float),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services.

    Args:
        hass: Home Assistant instance.
    """

    async def _reset_learning(call: ServiceCall) -> None:
        await _async_handle_reset_learning(hass, call)

    async def _calculate_anticipated_start_time(call: ServiceCall) -> dict[str, Any]:
        return await _async_handle_calculate_anticipated_start_time(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_LEARNING,
        _reset_learning,
        schema=RESET_LEARNING_SCHEMA,  # type: ignore[arg-type, unused-ignore]
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_ANTICIPATED_START_TIME,
        _calculate_anticipated_start_time,
        schema=CALCULATE_ANTICIPATED_START_TIME_SCHEMA,  # type: ignore[arg-type, unused-ignore]
        supports_response=SupportsResponse.ONLY,
    )


def _resolve_coordinator(hass: HomeAssistant, entity_id: str) -> HeatingApplication:
    """Resolve the loaded IHP coordinator owning an entity.

    Looks up the entity in the entity registry to find its config entry, then returns the
    corresponding HeatingApplication coordinator.

    Raises:
        ServiceValidationError: If the entity or its coordinator cannot be found, so callers
            receive immediate actionable feedback in the HA UI.
    """
    entity_entry = er.async_get(hass).async_get(entity_id)
    if not entity_entry:
        raise ServiceValidationError(
            f"Entity '{entity_id}' was not found in the Home Assistant entity registry. "
            "Please provide a valid IHP sensor entity ID, for example: "
            "sensor.intelligent_heating_pilot_<device_name>_anticipated_start_time."
        )
    coordinator = hass.data.get(DOMAIN, {}).get(entity_entry.config_entry_id)
    if not isinstance(coordinator, HeatingApplication):
        raise ServiceValidationError(
            f"No IHP device found for entity '{entity_id}' "
            f"(config_entry_id={entity_entry.config_entry_id}). "
            "Make sure the IHP integration is properly configured."
        )
    return coordinator


async def _async_handle_reset_learning(hass: HomeAssistant, call: ServiceCall) -> None:
    """Reset the learning data of the device owning the targeted entity.

    Resolving the device from the entity lets callers choose which device to reset when
    several IHP config entries exist.
    """
    _LOGGER.debug("Entering handle_reset_learning")

    coordinator = _resolve_coordinator(hass, call.data["entity_id"])
    if coordinator._orchestrator is None:
        raise ServiceValidationError("IHP is not initialized yet for this device.")
    try:
        await coordinator.async_reset_learning()
    except LearningResetError as err:
        raise HomeAssistantError(
            f"Learning reset incomplete for device {coordinator.get_device_id()}: {err}"
        ) from err
    _LOGGER.info("reset_learning: learning data cleared for device %s", coordinator.get_device_id())


def _vtherm_target_temp(hass: HomeAssistant, coordinator: HeatingApplication) -> Any:
    """Return the current VTherm setpoint, used when the caller gives no target."""
    vtherm_entity_id = coordinator.get_vtherm_entity()
    if not vtherm_entity_id:
        return None
    vtherm_state = hass.states.get(vtherm_entity_id)
    return vtherm_state.attributes.get("temperature") if vtherm_state else None


async def _async_handle_calculate_anticipated_start_time(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Calculate when a device must start heating to reach a target at a given time.

    Delegates to the orchestrator's calculate_anticipation_only(): no business logic here.
    """
    _LOGGER.debug("Entering handle_calculate_anticipated_start_time")

    target_time = call.data["target_time"]
    if target_time.tzinfo is None:
        target_time = dt_util.as_local(target_time)

    coordinator = _resolve_coordinator(hass, call.data["entity_id"])

    target_temp = call.data.get("target_temp")
    if target_temp is None:
        target_temp = _vtherm_target_temp(hass, coordinator)
    if target_temp is not None:
        target_temp = float(target_temp)

    if coordinator._orchestrator is None:
        raise ServiceValidationError("IHP is not initialized yet for this device.")

    anticipation_data = await coordinator._orchestrator.calculate_anticipation_only(
        target_time=target_time,
        target_temp=target_temp,
    )
    return _anticipation_response(anticipation_data, target_time, target_temp)


def _anticipation_response(
    anticipation_data: dict[str, Any], target_time: Any, target_temp: float | None
) -> dict[str, Any]:
    """Shape the orchestrator result as the service response."""
    anticipated_start_time = anticipation_data.get("anticipated_start_time")
    response_target_time = anticipation_data.get("next_schedule_time") or target_time
    response_target_temp = anticipation_data.get("next_target_temperature")
    if response_target_temp is None:
        response_target_temp = target_temp

    if anticipated_start_time is None:
        _LOGGER.warning("Could not calculate anticipated start time (insufficient data)")
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
    return {
        "anticipated_start_time": anticipated_start_time.isoformat(),
        "target_time": response_target_time.isoformat(),
        "target_temp": response_target_temp,
        "current_temp": anticipation_data.get("current_temp"),
        "estimated_duration_minutes": anticipation_data.get("estimated_duration_minutes"),
        "learned_heating_slope": anticipation_data.get("learned_heating_slope"),
        "confidence_level": anticipation_data.get("confidence_level"),
    }
