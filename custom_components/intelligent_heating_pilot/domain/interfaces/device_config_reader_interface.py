"""Device configuration reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceConfig:
    """Complete configuration for an IHP device.

    This is an immutable value object that holds all configuration parameters
    for a single IHP device. It is created by HADeviceConfigReader from
    Home Assistant config entries.

    Attributes:
        # Required fields
        device_id: Unique identifier for the device (typically config_entry.entry_id)
        vtherm_entity_id: Entity ID of the virtual thermostat (climate entity)

        # Optional entity IDs (environmental sensors)
        scheduler_entities: List of entity IDs for scheduled events (switches)
        humidity_in_entity_id: Entity ID for indoor humidity sensor (optional)
        humidity_out_entity_id: Entity ID for outdoor humidity sensor (optional)
        cloud_cover_entity_id: Entity ID for cloud coverage sensor (optional)

        # Learning and data retention parameters
        lhs_retention_days: Number of days to retain learned heating slope data
        dead_time_minutes: Dead time in minutes (delay before heating becomes effective)
        auto_learning: If True, automatically learn parameters from heating cycles

        # Cycle detection parameters
        temp_delta_threshold: Temperature delta threshold for cycle detection (°C)
        cycle_split_duration_minutes: Duration to split heating cycles (0 = disabled)
        min_cycle_duration_minutes: Minimum valid cycle duration
        max_cycle_duration_minutes: Maximum valid cycle duration

        # IHP control state
        ihp_enabled: If True, IHP preheating is active; if False, IHP is paused
        task_range_days: Number of days covered by each Recorder extraction task (tune to machine power)
        anticipation_recalc_tolerance_minutes: Absolute time delta threshold (minutes) used
                             to decide whether an active preheating should be
                             canceled and rescheduled.
        safety_shutoff_grace_minutes: Duration in minutes of the grace period for brief heating
                                      interruptions (safety/frost mode). Interruptions shorter than
                                      this threshold do not terminate an in-progress cycle, avoiding
                                      bogus dead-time and slope values. Set 0 to disable.
    """

    # Required fields
    device_id: str
    vtherm_entity_id: str

    # Optional entity IDs
    scheduler_entities: list[str]
    humidity_in_entity_id: str | None = None
    humidity_out_entity_id: str | None = None
    temperature_out_entity_id: str | None = None
    cloud_cover_entity_id: str | None = None

    # Learning and data retention
    lhs_retention_days: int = 30
    dead_time_minutes: float = 0.0
    auto_learning: bool = True

    # Cycle detection parameters
    temp_delta_threshold: float = 0.2
    cycle_split_duration_minutes: int = 0
    min_cycle_duration_minutes: int = 5
    max_cycle_duration_minutes: int = 300

    # IHP enabled state
    ihp_enabled: bool = True
    task_range_days: int = 7
    anticipation_recalc_tolerance_minutes: int = 15
    safety_shutoff_grace_minutes: int = 10

    def __post_init__(self) -> None:
        """Validate configuration values after initialization.

        Raises:
            ValueError: If any configuration value is invalid
        """
        # Validate required fields
        if not self.device_id or not isinstance(self.device_id, str):
            raise ValueError("device_id must be a non-empty string")

        if not self.vtherm_entity_id or not isinstance(self.vtherm_entity_id, str):
            raise ValueError("vtherm_entity_id must be a non-empty string")

        # Validate scheduler_entities is a list
        if not isinstance(self.scheduler_entities, list):
            raise ValueError("scheduler_entities must be a list")

        # Validate numeric ranges
        if self.lhs_retention_days < 0:
            raise ValueError("lhs_retention_days must be at least 0")

        if self.dead_time_minutes < 0:
            raise ValueError("dead_time_minutes must be at least 0")

        if self.temp_delta_threshold < 0:
            raise ValueError("temp_delta_threshold must be at least 0")

        if self.cycle_split_duration_minutes < 0:
            raise ValueError("cycle_split_duration_minutes must be at least 0")

        if self.min_cycle_duration_minutes < 1:
            raise ValueError("min_cycle_duration_minutes must be at least 1")

        if self.max_cycle_duration_minutes <= self.min_cycle_duration_minutes:
            raise ValueError("max_cycle_duration_minutes must be > min_cycle_duration_minutes")

        if self.task_range_days < 1:
            raise ValueError("task_range_days must be at least 1")

        if self.anticipation_recalc_tolerance_minutes < 0:
            raise ValueError("anticipation_recalc_tolerance_minutes must be at least 0")

        if self.safety_shutoff_grace_minutes < 0:
            raise ValueError("safety_shutoff_grace_minutes must be at least 0")


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
