"""Shared utility functions for infrastructure adapters."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_conversion import TemperatureConverter

_LOGGER = logging.getLogger(__name__)

WEATHER_DOMAIN = "weather"
WEATHER_ATTR_TEMPERATURE_UNIT = "temperature_unit"
# Numeric attributes exposed by weather entities, whose state is a condition string.
WEATHER_ATTR_TEMPERATURE = "temperature"
WEATHER_ATTR_HUMIDITY = "humidity"
WEATHER_ATTR_CLOUD_COVERAGE = "cloud_coverage"


def get_entity_name(hass: HomeAssistant, entity_id: str) -> str:
    """Get the friendly name of an entity, falling back to entity_id.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to get name for

    Returns:
        Friendly name or entity_id if not found
    """
    state = hass.states.get(entity_id)
    if state:
        return cast(str, state.attributes.get("friendly_name", entity_id))
    return entity_id


def read_numeric_state(state: State, weather_attribute: str) -> float | None:
    """Read a numeric value from a sensor state or a weather entity attribute.

    A sensor carries its value in the state, whereas a weather entity's state is a
    condition string (e.g. "cloudy") and the numbers live in attributes. Reading the
    state of a weather entity as a float would always fail.

    Args:
        state: Home Assistant state of the source entity
        weather_attribute: Attribute to read when the entity is a weather entity

    Returns:
        Float value, or None if missing or not numeric
    """
    # Attributes are untyped: a weather attribute can hold anything, or be missing
    raw: Any = (
        state.attributes.get(weather_attribute) if state.domain == WEATHER_DOMAIN else state.state
    )
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def read_temperature_celsius(state: State) -> float | None:
    """Read a temperature from a sensor or weather entity, converted to Celsius.

    The domain works in Celsius, but HA reports temperatures in the entity's own
    unit (``unit_of_measurement`` for a sensor, ``temperature_unit`` for a weather
    entity). A missing unit is assumed to already be Celsius.

    Args:
        state: Home Assistant state of the source entity

    Returns:
        Temperature in Celsius, or None if missing, not numeric or in an unknown unit
    """
    value = read_numeric_state(state, WEATHER_ATTR_TEMPERATURE)
    if value is None:
        return None
    unit = temperature_unit(state.domain, state.attributes)
    celsius = to_celsius(value, unit)
    if celsius is None:
        _LOGGER.warning("Unsupported temperature unit %s for %s", unit, state.entity_id)
    return celsius


def temperature_unit(domain: str, attributes: Mapping[str, Any]) -> str | None:
    """Return the temperature unit an entity reports its temperature in.

    Args:
        domain: Entity domain ("weather" or a sensor domain)
        attributes: Entity state attributes

    Returns:
        Unit string, or None when the entity does not state one
    """
    unit_attribute = (
        WEATHER_ATTR_TEMPERATURE_UNIT if domain == WEATHER_DOMAIN else ATTR_UNIT_OF_MEASUREMENT
    )
    unit = attributes.get(unit_attribute)
    return str(unit) if unit else None


def to_celsius(value: float, unit: str | None) -> float | None:
    """Convert a temperature to Celsius.

    Args:
        value: Temperature in ``unit``
        unit: Source unit; None is assumed to already be Celsius

    Returns:
        Temperature in Celsius, or None if the unit cannot be converted
    """
    if not unit or unit == UnitOfTemperature.CELSIUS:
        return value
    try:
        return float(TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS))
    except HomeAssistantError:
        return None
