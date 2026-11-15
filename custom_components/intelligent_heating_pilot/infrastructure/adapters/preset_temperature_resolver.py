"""Home Assistant preset temperature resolver.

Implements IPresetTemperatureResolver by reading what the VTherm entity publishes for a
preset. It was part of the scheduler reader; the wake-up sources need it too, and an adapter
should not be reached through another adapter's private method.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ...domain.interfaces.preset_temperature_resolver_interface import IPresetTemperatureResolver
from ..vtherm_compat import get_vtherm_attribute

_LOGGER = logging.getLogger(__name__)


class HAPresetTemperatureResolver(IPresetTemperatureResolver):
    """Tells which temperature a VTherm preset stands for, from its published attributes."""

    def __init__(self, hass: HomeAssistant, vtherm_entity_id: str | None) -> None:
        """Initialize the resolver.

        Args:
            hass: Home Assistant instance.
            vtherm_entity_id: The VTherm climate entity whose attributes are read.
        """
        self._hass = hass
        self._vtherm_entity_id = vtherm_entity_id

    def resolve(self, preset: str) -> float | None:
        """Resolve a preset name to a numeric temperature using VTherm attributes.

        This uses the VTherm climate entity attributes as the source of truth. It
        attempts common attribute naming conventions, with v8.0.0+ compatibility
        using get_vtherm_attribute() to access both legacy and new data structures.

        Args:
            preset: Preset mode name from the scheduler action

        Returns:
            Temperature in Celsius, or None if it cannot be resolved.
        """
        if not self._vtherm_entity_id:
            return None
        state = self._hass.states.get(self._vtherm_entity_id)
        if not state:
            _LOGGER.debug("VTherm entity not found: %s", self._vtherm_entity_id)
            return None

        key = str(preset).lower().replace(" ", "_")

        # First, try the preset_temperatures dict (VTherm v8.0.0+ format)
        preset_temps = get_vtherm_attribute(state, "preset_temperatures")
        if isinstance(preset_temps, dict):
            # VTherm uses format like "eco_temp", "boost_temp", "comfort_temp"
            # Try multiple key patterns
            preset_keys_to_try = [
                f"{key}_temp",  # eco_temp, boost_temp
                f"{key}_temperature",  # eco_temperature
                key,  # eco, boost (fallback)
                preset.lower(),  # Original lowercase
            ]

            for preset_key in preset_keys_to_try:
                if preset_key in preset_temps:
                    try:
                        temp_value = float(preset_temps[preset_key])
                        # Ignore 0 values as they indicate uninitialized presets
                        if temp_value > 0:
                            _LOGGER.debug(
                                "Resolved preset '%s' to %.1f°C (from %s)",
                                preset,
                                temp_value,
                                preset_key,
                            )
                            return temp_value
                        else:
                            _LOGGER.debug(
                                "Skipping preset '%s' with 0°C (likely uninitialized)", preset
                            )
                    except (ValueError, TypeError):
                        _LOGGER.debug(
                            "Invalid preset_temperatures value for %s: %s",
                            preset_key,
                            preset_temps[preset_key],
                        )

        # Fallback: try common naming patterns with v8.0.0+ compatibility
        candidate_keys = [
            f"{key}_temperature",
            f"{key}_temp",
            f"temperature_{key}",
            f"temp_{key}",
        ]

        for k in candidate_keys:
            # Use get_vtherm_attribute to handle both legacy and v8.0.0+ formats
            value = get_vtherm_attribute(state, k)
            if value is not None:
                try:
                    temp_value = float(value)
                except (ValueError, TypeError):
                    _LOGGER.debug("Invalid preset attribute %s=%s", k, value)
                    continue
                # Ignore 0 values as they indicate uninitialized presets
                if temp_value > 0:
                    return temp_value
                _LOGGER.debug("Skipping preset attribute %s with 0°C (likely uninitialized)", k)

        # Fallback: if this preset is currently active, use current target temperature
        current_preset = get_vtherm_attribute(state, "preset_mode")
        if isinstance(current_preset, str) and current_preset.lower() == key:
            for target_key in ("temperature", "target_temperature", "target_temp"):
                value = get_vtherm_attribute(state, target_key)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass

        return None
