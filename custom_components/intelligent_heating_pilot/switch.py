"""Switch platform for Intelligent Heating Pilot."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME, DOMAIN

if TYPE_CHECKING:
    from . import IntelligentHeatingPilotCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Intelligent Heating Pilot switch."""
    coordinator: IntelligentHeatingPilotCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    name = config_entry.data.get(CONF_NAME, "Intelligent Heating Pilot")

    switches = [
        IntelligentHeatingPilotEnableSwitch(coordinator, config_entry, name),
    ]

    async_add_entities(switches, True)


class IntelligentHeatingPilotEnableSwitch(SwitchEntity):
    """Switch to enable or disable IHP preheating."""

    _attr_has_entity_name = True
    _attr_name = "IHP Preheating"
    _attr_icon = "mdi:home-thermometer"

    def __init__(
        self, 
        coordinator: IntelligentHeatingPilotCoordinator, 
        config_entry: ConfigEntry, 
        name: str
    ) -> None:
        """Initialize the switch."""
        self.coordinator = coordinator
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_preheating_enabled"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": name,
            "manufacturer": "Intelligent Heating Pilot",
            "model": "Intelligent Preheating with ML",
        }

    @property
    def is_on(self) -> bool:
        """Return true if IHP is enabled."""
        return self.coordinator.is_ihp_enabled()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on IHP preheating."""
        _LOGGER.info("Enabling IHP preheating")
        await self.coordinator.set_ihp_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off IHP preheating."""
        _LOGGER.info("Disabling IHP preheating")
        await self.coordinator.set_ihp_enabled(False)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "description": "Enable or disable IHP intelligent preheating. "
                          "When disabled, IHP continues learning and calculating but does not "
                          "trigger scheduler actions for preheating.",
        }
