"""Home Assistant preset temperature resolver.

Implements IPresetTemperatureResolver for any climate entity. Versatile Thermostat publishes
the temperature behind each preset; a standard climate only exposes its ``preset_modes``, so the
user tells IHP which temperature each preset stands for. It was part of the scheduler reader; the
wake-up sources need it too, and an adapter should not be reached through another adapter's
private method.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant, State

from ...domain.interfaces.preset_temperature_resolver_interface import IPresetTemperatureResolver
from ..climate_attributes import get_climate_attribute

_LOGGER = logging.getLogger(__name__)


def normalize_preset(preset: str) -> str:
    """Return the form of a preset name that is compared, whatever its case or padding."""
    return str(preset).strip().lower()


class HAPresetTemperatureResolver(IPresetTemperatureResolver):
    """Tells which temperature a preset stands for, from the climate or from the user."""

    def __init__(
        self,
        hass: HomeAssistant,
        climate_entity_id: str | None,
        configured_temperatures: Mapping[str, float] | None = None,
    ) -> None:
        """Initialize the resolver.

        Args:
            hass: Home Assistant instance.
            climate_entity_id: The climate entity whose attributes are read.
            configured_temperatures: The temperature the user mapped to each preset, for the
                climates that do not publish it.
        """
        self._hass = hass
        self._climate_entity_id = climate_entity_id
        self._configured = {
            normalize_preset(preset): temperature
            for preset, temperature in (configured_temperatures or {}).items()
        }
        self._warned: set[str] = set()

    def resolve(self, preset: str) -> float | None:
        """Resolve a preset name to a numeric temperature.

        The order is: what the climate publishes (the source of truth for Versatile
        Thermostat), what the user mapped, then the target of the climate while the preset
        is active. An unresolved preset is reported once.

        Args:
            preset: Preset mode name from the scheduler action

        Returns:
            Temperature in Celsius, or None if it cannot be resolved.
        """
        state = self._hass.states.get(self._climate_entity_id) if self._climate_entity_id else None
        key = str(preset).lower().replace(" ", "_")

        temperature = self._published_temperature(state, preset, key)
        if temperature is None:
            temperature = self._configured_temperature(preset)
        if temperature is None:
            temperature = self._active_preset_target(state, key)
        if temperature is None:
            self._warn_unresolved(preset)
        return temperature

    def _configured_temperature(self, preset: str) -> float | None:
        """Return the temperature the user mapped to a preset, when it is a number."""
        value = self._configured.get(normalize_preset(preset))
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            _LOGGER.debug("Invalid mapped temperature for preset '%s': %s", preset, value)
            return None

    def _warn_unresolved(self, preset: str) -> None:
        """Say once per preset that no temperature is known, so no slot silently vanishes."""
        marker = normalize_preset(preset)
        if marker in self._warned:
            return
        self._warned.add(marker)
        _LOGGER.warning(
            "Cannot tell which temperature the preset '%s' of %s stands for: slots that use it "
            "are not anticipated. Map the preset to a temperature in the IHP options.",
            preset,
            self._climate_entity_id,
        )

    def _published_temperature(self, state: State | None, preset: str, key: str) -> float | None:
        """Return the temperature the climate itself publishes for a preset."""
        if state is None:
            return None
        preset_temps = get_climate_attribute(state, "preset_temperatures")
        if isinstance(preset_temps, dict):
            # VTherm uses format like "eco_temp", "boost_temp", "comfort_temp"
            for preset_key in (f"{key}_temp", f"{key}_temperature", key, preset.lower()):
                temperature = self._positive_float(preset_temps.get(preset_key), preset_key)
                if temperature is not None:
                    _LOGGER.debug("Resolved preset '%s' to %.1f°C", preset, temperature)
                    return temperature

        for attribute in (
            f"{key}_temperature",
            f"{key}_temp",
            f"temperature_{key}",
            f"temp_{key}",
        ):
            value = get_climate_attribute(state, attribute)
            temperature = self._positive_float(value, attribute)
            if temperature is not None:
                return temperature
        return None

    @staticmethod
    def _positive_float(value: Any, name: str) -> float | None:
        """Return a published value as a temperature, ignoring unset (0) and invalid ones."""
        if value is None:
            return None
        try:
            temperature = float(value)
        except (TypeError, ValueError):
            _LOGGER.debug("Invalid preset temperature %s=%s", name, value)
            return None
        if temperature > 0:
            return temperature
        # 0 means the preset was never set on the thermostat
        _LOGGER.debug("Skipping preset temperature %s at 0°C (likely uninitialized)", name)
        return None

    @staticmethod
    def _active_preset_target(state: State | None, key: str) -> float | None:
        """Return the target of the climate when the asked preset is the active one."""
        if state is None:
            return None
        current_preset = get_climate_attribute(state, "preset_mode")
        if not (isinstance(current_preset, str) and current_preset.lower() == key):
            return None
        for target_key in ("temperature", "target_temperature", "target_temp"):
            value = get_climate_attribute(state, target_key)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        return None
