"""Factory for HeatingCycleLifecycleManager - wires dependencies with DDD compliance."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..domain.interfaces.device_config_reader_interface import DeviceConfig
from ..domain.interfaces.historical_data_adapter_interface import IHistoricalDataAdapter
from ..infrastructure.adapters.climate_data_reader import HAClimateDataReader
from ..infrastructure.adapters.entity_attribute_mapper_registry import (
    EntityAttributeMapperRegistry,
)
from ..infrastructure.adapters.vtherm_attribute_mapper import VThermAttributeMapper
from ..infrastructure.recorder_queue import get_extraction_semaphore, get_recorder_queue
from .heating_cycle_lifecycle_manager import HeatingCycleLifecycleManager

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..domain.interfaces import IHeatingCycleStorage, ILhsStorage, ITimerScheduler
    from ..domain.interfaces.heating_cycle_service_interface import IHeatingCycleService
    from .lhs_lifecycle_manager import LhsLifecycleManager

_LOGGER = logging.getLogger(__name__)


class HeatingCycleLifecycleManagerFactory:
    """Factory for creating HeatingCycleLifecycleManager with singleton pattern.

    Singleton Pattern:
    - **One instance per device_id**: Each IHP device gets its own manager instance
    - **Shared across requests**: Multiple calls with same device_id return same instance
    - **Thread-safe**: Factory maintains internal registry to track instances

    Dependency Wiring:
    - Injects all required dependencies (heating_cycle_service, adapters, caches)
    - Optionally injects LhsLifecycleManager for cascade updates
    - Ensures DDD compliance (domain services, infrastructure adapters)

    Usage:
    ```python
    # First call creates instance
    manager1 = factory.create(hass, device_config, ...)

    # Second call with same device_id returns same instance
    manager2 = factory.create(hass, device_config, ...)
    assert manager1 is manager2  # True
    ```
    """

    # Class-level registry: device_id -> HeatingCycleLifecycleManager instance
    _instances: dict[str, HeatingCycleLifecycleManager] = {}

    @classmethod
    def create(
        cls,
        hass: HomeAssistant,
        device_config: DeviceConfig,
        heating_cycle_service: IHeatingCycleService,
        cycle_cache: IHeatingCycleStorage | None = None,
        timer_scheduler: ITimerScheduler | None = None,
        model_storage: ILhsStorage | None = None,
        lhs_lifecycle_manager: LhsLifecycleManager | None = None,
        dead_time_updated_callback: Callable[[float], None] | None = None,
    ) -> HeatingCycleLifecycleManager:
        """Create or return existing HeatingCycleLifecycleManager for device_id.

        Singleton Behavior:
        - If instance exists for device_config.device_id, returns existing instance
        - If no instance exists, creates new one and stores in registry
        - Registry is class-level, shared across all factory instances

        Dependency Injection:
        - heating_cycle_service: Domain service for extracting cycles from historical data
        - cycle_cache: Infrastructure adapter for persistent cycle storage
        - timer_scheduler: Infrastructure adapter for scheduling 24h refresh
        - model_storage: Infrastructure adapter for persisting individual cycles
        - lhs_lifecycle_manager: Application service for cascade LHS updates

        Args:
            hass: Home Assistant instance (used for historical data adapters).
            device_config: Device configuration (contains device_id for singleton key).
            heating_cycle_service: Service for extracting heating cycles.
            cycle_cache: Optional persistent cache for incremental cycle storage.
            timer_scheduler: Optional scheduler for periodic 24h refresh.
            model_storage: Optional persistent storage for individual cycle records.
            lhs_lifecycle_manager: Optional LHS manager for cascade updates.
            dead_time_updated_callback: Optional callback fired after dead time persistence.

        Returns:
            Singleton HeatingCycleLifecycleManager instance for the device_id.
        """
        device_id = device_config.device_id

        # Check if instance already exists
        if device_id in cls._instances:
            _LOGGER.debug(
                "Returning existing HeatingCycleLifecycleManager for device_id=%s", device_id
            )
            return cls._instances[device_id]

        # Create new instance
        _LOGGER.debug("Creating new HeatingCycleLifecycleManager for device_id=%s", device_id)

        # Wire historical data adapters from hass infrastructure
        # Dynamically detect entity type (VTherm vs generic climate) for diagnostics
        _LOGGER.debug(
            "Setting up historical data adapters for device_id=%s", device_config.device_id
        )
        vtherm_entity_id = device_config.vtherm_entity_id
        _LOGGER.debug("Configured VTherm entity_id: %s", vtherm_entity_id)

        # Detect entity type (VTherm or generic climate) for diagnostic logging
        entity_type = cls._detect_entity_type(hass, vtherm_entity_id)
        _LOGGER.info(
            "Detected entity type for %s: %s (auto-detection)",
            vtherm_entity_id,
            entity_type,
        )

        climate_adapter = HAClimateDataReader(hass, get_recorder_queue(hass), vtherm_entity_id)
        historical_adapters: list[IHistoricalDataAdapter] = [climate_adapter]
        _LOGGER.debug(
            "Configured %d historical adapter(s) for device_id=%s with dynamic entity detection",
            len(historical_adapters),
            device_config.device_id,
        )

        manager = HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=heating_cycle_service,
            historical_adapters=historical_adapters,
            heating_cycle_storage=cycle_cache,
            timer_scheduler=timer_scheduler,
            lhs_storage=model_storage,
            lhs_lifecycle_manager=lhs_lifecycle_manager,
            dead_time_updated_callback=dead_time_updated_callback,
            extraction_semaphore=get_extraction_semaphore(hass),
        )

        # Store in registry
        cls._instances[device_id] = manager
        _LOGGER.debug("Registered HeatingCycleLifecycleManager for device_id=%s", device_id)

        return manager

    @classmethod
    def _detect_entity_type(cls, hass: HomeAssistant, vtherm_entity_id: str) -> str:
        """Detect the type of climate entity (VTherm or generic climate).

        Uses EntityAttributeMapperRegistry to auto-detect the entity type.
        Used for diagnostic logging and validation.

        Args:
            hass: Home Assistant instance
            vtherm_entity_id: Entity ID to detect

        Returns:
            String describing the entity type (e.g., "VTherm v8.0+", "Generic Climate")
        """
        try:
            mapper_registry = EntityAttributeMapperRegistry(hass)
            mapper = mapper_registry.get_mapper_for_entity(vtherm_entity_id)

            # Identify mapper type for logging
            if isinstance(mapper, VThermAttributeMapper):
                return "VTherm (Versatile Thermostat)"
            return "Generic Climate"
        except ValueError as e:
            _LOGGER.warning(
                "Could not detect entity type for %s: %s",
                vtherm_entity_id,
                str(e),
            )
            return "Unknown"

    @classmethod
    def reset_instances(cls) -> None:
        """Clear singleton registry (for testing only).

        Use Case:
        Called in test teardown to ensure clean state between tests.
        Should NOT be used in production code.
        """
        cls._instances = {}
        _LOGGER.debug("Reset HeatingCycleLifecycleManager singleton registry")
