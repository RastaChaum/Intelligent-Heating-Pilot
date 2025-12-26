"""Home Assistant device configuration reader adapter."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.device_config_reader import DeviceConfig, IDeviceConfigReader
from ...const import (
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_LHS_RETENTION_DAYS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class HADeviceConfigReader(IDeviceConfigReader):
    """Home Assistant implementation of device configuration reader.
    
    Reads configuration from Home Assistant config entries for IHP devices.
    Since IHP is a single-device integration per config entry, device_id
    corresponds to the config entry ID.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the device config reader.
        
        Args:
            hass: Home Assistant instance
            config_entry: The config entry for this IHP integration instance
        """
        self._hass = hass
        self._config_entry = config_entry

    async def get_device_config(self, device_id: str) -> DeviceConfig:
        """Retrieve configuration for a specific device.
        
        Args:
            device_id: The device identifier (corresponds to config entry ID)
            
        Returns:
            DeviceConfig with all necessary entity mappings
            
        Raises:
            ValueError: If device_id doesn't match or configuration is invalid
        """
        _LOGGER.debug("Retrieving device configuration for device_id=%s", device_id)

        # In the IHP architecture, device_id corresponds to the config entry ID
        if device_id != self._config_entry.entry_id:
            raise ValueError(
                f"Device ID {device_id} not found. "
                f"This integration instance manages device {self._config_entry.entry_id}"
            )

        # Extract configuration with options override support
        config = dict(self._config_entry.data)
        options = dict(self._config_entry.options)

        vtherm_entity = self._get_config_value(config, options, CONF_VTHERM_ENTITY)
        if not vtherm_entity:
            raise ValueError("Missing required vtherm_entity_id in configuration")

        scheduler_entities = self._get_scheduler_entities(config, options)
        if not scheduler_entities:
            raise ValueError("Missing required scheduler_entities in configuration")

        humidity_in = self._get_config_value(config, options, CONF_HUMIDITY_IN_ENTITY)
        humidity_out = self._get_config_value(config, options, CONF_HUMIDITY_OUT_ENTITY)
        cloud_cover = self._get_config_value(config, options, CONF_CLOUD_COVER_ENTITY)

        lhs_retention_days = int(
            self._get_config_value(config, options, CONF_LHS_RETENTION_DAYS)
            or DEFAULT_LHS_RETENTION_DAYS
        )

        device_config = DeviceConfig(
            device_id=device_id,
            vtherm_entity_id=vtherm_entity,
            scheduler_entities=scheduler_entities,
            humidity_in_entity_id=humidity_in,
            humidity_out_entity_id=humidity_out,
            cloud_cover_entity_id=cloud_cover,
            lhs_retention_days=lhs_retention_days,
        )

        _LOGGER.debug("Retrieved device configuration: %s", device_config)
        return device_config

    async def get_all_device_ids(self) -> list[str]:
        """Retrieve list of all configured device IDs.
        
        In IHP architecture, there's typically one device per config entry,
        so this returns a single-element list.
        
        Returns:
            List containing the config entry ID
        """
        return [self._config_entry.entry_id]

    @staticmethod
    def _get_config_value(
        config: dict[str, Any], options: dict[str, Any], key: str
    ) -> str | None:
        """Get configuration value with options override support.
        
        Options take precedence over config data.
        """
        return options.get(key) or config.get(key)

    @staticmethod
    def _get_scheduler_entities(config: dict[str, Any], options: dict[str, Any]) -> list[str]:
        """Extract scheduler entities from configuration.
        
        Returns list of entity IDs, or empty list if not found.
        """
        scheduler_entities = (
            options.get(CONF_SCHEDULER_ENTITIES)
            or config.get(CONF_SCHEDULER_ENTITIES)
            or []
        )
        return list(scheduler_entities) if scheduler_entities else []
