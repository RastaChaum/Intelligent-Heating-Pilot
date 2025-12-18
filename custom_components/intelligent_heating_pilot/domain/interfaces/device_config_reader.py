"""Device configuration reader interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceConfig:
    """Configuration for an IHP device.
    
    Attributes:
        device_id: Unique identifier for the device
        vtherm_entity_id: Entity ID of the virtual thermostat (climate entity)
        scheduler_entities: List of entity IDs for scheduled events
        humidity_in_entity_id: Entity ID for indoor humidity (optional)
        humidity_out_entity_id: Entity ID for outdoor humidity (optional)
        cloud_cover_entity_id: Entity ID for cloud coverage (optional)
        lhs_retention_days: Number of days to retain slope data
    """
    device_id: str
    vtherm_entity_id: str
    scheduler_entities: list[str]
    humidity_in_entity_id: str | None = None
    humidity_out_entity_id: str | None = None
    cloud_cover_entity_id: str | None = None
    lhs_retention_days: int = 30


class IDeviceConfigReader(ABC):
    """Contract for reading device configuration.
    
    Implementations should retrieve configuration for a specific IHP device,
    including entity IDs for climate control, scheduling, and environmental sensors.
    """

    @abstractmethod
    async def get_device_config(self, device_id: str) -> DeviceConfig:
        """Retrieve configuration for a specific device.
        
        Args:
            device_id: The device identifier to retrieve configuration for
            
        Returns:
            DeviceConfig with all necessary entity mappings
            
        Raises:
            ValueError: If device_id is not found or configuration is invalid
        """
        pass

    @abstractmethod
    async def get_all_device_ids(self) -> list[str]:
        """Retrieve list of all configured device IDs.
        
        Returns:
            List of configured device IDs
        """
        pass
