"""Home Assistant climate commander adapter.

Implements IClimateCommander: it writes a slot action to the one climate entity IHP preheats.
It only translates domain requests into climate service calls; every decision (whether to
apply, what to restore) was already taken by the domain policy.
"""

from __future__ import annotations

import logging

from homeassistant.core import Context, HomeAssistant

from ...domain.interfaces.climate_commander_interface import IClimateCommander
from ...domain.value_objects.restore_fields import RestoreFields
from ...domain.value_objects.slot_action import SlotAction, SlotActionKind
from .utils import get_entity_name

_LOGGER = logging.getLogger(__name__)

CLIMATE_DOMAIN = "climate"
SERVICE_SET_PRESET_MODE = "set_preset_mode"
SERVICE_SET_TEMPERATURE = "set_temperature"


class HAClimateCommander(IClimateCommander):
    """Writes to the climate entity (VTherm or any climate) from the domain layer.

    Every command carries a context that has a parent, the way an automation's does.
    Schedulers that watch for manual changes (ha-chauffage) ignore such a change, whereas a
    command with no parent looks like somebody turning the knob and would start an override.
    """

    def __init__(self, hass: HomeAssistant, climate_entity_id: str) -> None:
        """Initialize the climate commander.

        Args:
            hass: Home Assistant instance.
            climate_entity_id: The climate entity to control; the only one ever addressed.
        """
        self._hass = hass
        self._climate_entity_id = climate_entity_id
        self._device_name = get_entity_name(hass, climate_entity_id)

    async def apply(self, action: SlotAction) -> None:
        """Apply a slot action: a preset as a preset, a temperature as a temperature.

        Args:
            action: The action to apply; the preset wins when it carries both.
        """
        if action.applied_kind is SlotActionKind.PRESET and action.preset is not None:
            _LOGGER.info("[%s] Applying preset %s", self._device_name, action.preset)
            await self._set_preset(action.preset)
        elif action.temperature is not None:
            _LOGGER.info("[%s] Applying temperature %.1f°C", self._device_name, action.temperature)
            await self._set_temperature(action.temperature)

    async def restore(self, fields: RestoreFields) -> None:
        """Write back the given fields only; the HVAC mode is never written.

        Args:
            fields: The preset or temperature to set again; nothing is sent when empty.
        """
        if fields.preset is not None:
            _LOGGER.info("[%s] Restoring preset %s", self._device_name, fields.preset)
            await self._set_preset(fields.preset)
        elif fields.temperature is not None:
            _LOGGER.info("[%s] Restoring temperature %.1f°C", self._device_name, fields.temperature)
            await self._set_temperature(fields.temperature)

    async def _set_preset(self, preset: str) -> None:
        await self._call(SERVICE_SET_PRESET_MODE, {"preset_mode": preset})

    async def _set_temperature(self, temperature: float) -> None:
        await self._call(SERVICE_SET_TEMPERATURE, {"temperature": temperature})

    async def _call(self, service: str, data: dict[str, object]) -> None:
        await self._hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {"entity_id": self._climate_entity_id, **data},
            blocking=True,
            context=self._new_context(),
        )

    @staticmethod
    def _new_context() -> Context:
        """Build a context whose parent makes the command look like an automation's."""
        return Context(parent_id=Context().id)
