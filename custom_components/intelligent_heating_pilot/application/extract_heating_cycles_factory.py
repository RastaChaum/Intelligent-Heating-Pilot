"""Factory for ExtractHeatingCyclesUseCase - wires dependencies with DDD compliance.

This factory:
- Creates infrastructure adapters (historical data sources)
- Extracts domain service from application service
- Wires everything into the use case
- Ensures separation of concerns
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..domain.interfaces.device_config_reader_interface import DeviceConfig
from ..infrastructure.adapters import (
    ClimateDataAdapter,
    SensorDataAdapter,
    WeatherDataAdapter,
)
from .extract_heating_cycles_use_case import ExtractHeatingCyclesUseCase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..domain.interfaces import ICycleCache, ITimerScheduler
    from . import HeatingApplicationService

_LOGGER = logging.getLogger(__name__)


class ExtractHeatingCyclesUseCaseFactory:
    """Factory for creating ExtractHeatingCyclesUseCase with all dependencies wired.

    Responsibilities:
    - Create infrastructure adapters (ClimateDataAdapter, SensorDataAdapter, etc.)
    - Extract domain service from application service
    - Wire all dependencies into use case
    - Maintain DDD separation (adapters stay in infrastructure layer)

    This avoids coupling coordinator directly to adapter creation.
    """

    @staticmethod
    def create(
        hass: HomeAssistant,
        app_service: HeatingApplicationService,
        device_config: DeviceConfig,
        cycle_cache: ICycleCache | None = None,
        timer_scheduler: ITimerScheduler | None = None,
    ) -> ExtractHeatingCyclesUseCase:
        """Create and wire ExtractHeatingCyclesUseCase with all dependencies.

        Args:
            hass: Home Assistant instance
            app_service: Application service containing heating_cycle_service
            device_config: Device configuration value object
            cycle_cache: Optional cache for incremental updates
            timer_scheduler: Optional timer for periodic refresh

        Returns:
            Fully configured ExtractHeatingCyclesUseCase instance
        """
        _LOGGER.debug(
            "Creating ExtractHeatingCyclesUseCase with factory for device=%s",
            device_config.device_id,
        )

        # Create infrastructure adapters (historical data sources)
        # These are in infrastructure layer but orchestrated by factory
        historical_adapters = [
            ClimateDataAdapter(hass),
            SensorDataAdapter(hass),
            WeatherDataAdapter(hass),
        ]

        _LOGGER.debug(
            "Created historical adapters: %d adapters for historical data extraction",
            len(historical_adapters),
        )

        # Extract domain service from application service
        heating_cycle_service = app_service.get_heating_cycle_service()

        _LOGGER.debug(
            "Extracted heating_cycle_service from application service",
        )

        # Create use case with all wired dependencies
        # Arguments match the ExtractHeatingCyclesUseCase.__init__ signature
        use_case = ExtractHeatingCyclesUseCase(
            device_config=device_config,
            heating_cycle_service=heating_cycle_service,
            historical_adapters=historical_adapters,
            cycle_cache=cycle_cache,
            timer_scheduler=timer_scheduler,
        )

        _LOGGER.debug(
            "ExtractHeatingCyclesUseCase created and configured for device=%s",
            device_config.device_id,
        )

        return use_case
