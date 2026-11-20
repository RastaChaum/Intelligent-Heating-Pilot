"""Options flow step that maps the presets of a generic climate to temperatures (#252).

Versatile Thermostat publishes the temperature behind each preset; a standard climate only lists
its ``preset_modes``. IHP needs that temperature to anticipate a slot that sets a preset, so the
user states it here, one field per preset. The step only collects the input: the stored mapping is
read back by the device config reader and used by the preset resolver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .config_flow_wake_up import MAX_TARGET_TEMPERATURE_C, MIN_TARGET_TEMPERATURE_C
from .const import CONF_CLIMATE_ENTITY, CONF_PRESET_TEMPERATURES
from .infrastructure.climate_attributes import get_climate_attribute

# HA's "no preset": a state, not a preset someone anticipates
PRESET_NONE = "none"
PRESET_STEP_C = 0.5


def mappable_presets(hass: HomeAssistant, climate: str | None) -> list[str]:
    """Return the presets whose temperature the user has to tell IHP.

    A climate that publishes its preset temperatures (Versatile Thermostat) needs no mapping,
    and neither does one without presets or that is not available yet.

    Args:
        hass: Home Assistant instance.
        climate: The climate entity the device preheats.

    Returns:
        The preset names to map; empty when no mapping is useful.
    """
    state = hass.states.get(climate) if climate else None
    if state is None or isinstance(get_climate_attribute(state, "preset_temperatures"), dict):
        return []
    presets = state.attributes.get("preset_modes")
    if not isinstance(presets, list):
        return []
    return [str(p) for p in presets if str(p).strip().lower() != PRESET_NONE]


def build_preset_schema(presets: list[str], saved: dict[str, Any]) -> vol.Schema:
    """Build the form: one optional temperature per preset, pre-filled when saved.

    Args:
        presets: The presets of the climate.
        saved: The mapping already stored, {preset: temperature}.

    Returns:
        The form schema.
    """
    fields: dict[Any, Any] = {}
    for preset in presets:
        value = saved.get(preset)
        fields[vol.Optional(preset, description={"suggested_value": value} if value else {})] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_TARGET_TEMPERATURE_C,
                    max=MAX_TARGET_TEMPERATURE_C,
                    step=PRESET_STEP_C,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        )
    return vol.Schema(fields)


def clean_preset_input(user_input: dict[str, Any], presets: list[str]) -> dict[str, float]:
    """Keep the filled temperatures of the known presets, so a cleared field leaves the mapping."""
    return {
        preset: float(user_input[preset])
        for preset in presets
        if user_input.get(preset) not in (None, "")
    }


class PresetTemperaturesFlowMixin:
    """The form that maps presets to temperatures, for the options flow.

    The host flow provides ``hass``, the pending options and what follows the step.
    """

    hass: HomeAssistant
    _pending: dict[str, Any]

    if TYPE_CHECKING:
        # Provided by the host options flow; declared here for the type checker only.
        async def _after_preset_temperatures(self) -> ConfigFlowResult: ...

        def async_show_form(self, **kwargs: Any) -> ConfigFlowResult: ...

    async def async_step_preset_temperatures(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the temperature of each preset, then go on with the options."""
        presets = mappable_presets(self.hass, self._pending.get(CONF_CLIMATE_ENTITY))
        if user_input is not None:
            self._pending[CONF_PRESET_TEMPERATURES] = clean_preset_input(user_input, presets)
            return await self._after_preset_temperatures()
        saved = self._pending.get(CONF_PRESET_TEMPERATURES)
        return self.async_show_form(
            step_id="preset_temperatures",
            data_schema=build_preset_schema(presets, saved if isinstance(saved, dict) else {}),
        )
