"""Use case for extracting heating cycles via REST API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..domain.interfaces.device_config_reader import IDeviceConfigReader
from ..domain.interfaces.heating_cycle_service import IHeatingCycleService
from ..domain.value_objects import HistoricalDataKey, HistoricalDataSet
from ..domain.value_objects.heating import HeatingCycle

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from ..infrastructure.adapters import (
        ClimateDataAdapter,
        SensorDataAdapter,
        WeatherDataAdapter,
    )

_LOGGER = logging.getLogger(__name__)


class ExtractHeatingCyclesUseCase:
    """Use case for extracting heating cycles from historical data.
    
    This orchestrates the process of:
    1. Retrieving device configuration
    2. Fetching historical data for the device's entities
    3. Extracting heating cycles using the domain service
    4. Returning formatted results
    """

    def __init__(
        self,
        device_config_reader: IDeviceConfigReader,
        heating_cycle_service: IHeatingCycleService,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the use case.
        
        Args:
            device_config_reader: Reader for device configuration
            heating_cycle_service: Domain service for cycle extraction
            hass: Home Assistant instance (for creating data adapters)
        """
        self._config_reader = device_config_reader
        self._cycle_service = heating_cycle_service
        self._hass = hass

    async def execute(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        cycle_split_duration_minutes: int | None = None,
    ) -> list[HeatingCycle]:
        """Execute the heating cycle extraction use case.
        
        Args:
            device_id: The device ID to extract cycles for
            start_time: Start of the time range for extraction
            end_time: End of the time range for extraction
            cycle_split_duration_minutes: Optional duration to split long cycles
            
        Returns:
            List of extracted HeatingCycle value objects
            
        Raises:
            ValueError: If device not found or data cannot be fetched
        """
        _LOGGER.info(
            "Executing heating cycle extraction for device=%s, start=%s, end=%s",
            device_id,
            start_time,
            end_time,
        )

        # Step 1: Get device configuration
        device_config = await self._config_reader.get_device_config(device_id)
        _LOGGER.debug("Retrieved device configuration: %s", device_config)

        # Step 2: Fetch historical data from all relevant entities
        historical_data_set = await self._fetch_historical_data(
            device_config, start_time, end_time
        )
        _LOGGER.debug("Fetched historical data with %d data keys", len(historical_data_set.data))

        # Step 3: Extract heating cycles
        cycles = await self._cycle_service.extract_heating_cycles(
            device_id=device_id,
            history_data_set=historical_data_set,
            start_time=start_time,
            end_time=end_time,
            cycle_split_duration_minutes=cycle_split_duration_minutes,
        )

        _LOGGER.info("Extracted %d heating cycles for device=%s", len(cycles), device_id)
        return cycles

    async def _fetch_historical_data(
        self, device_config, start_time: datetime, end_time: datetime
    ) -> HistoricalDataSet:
        """Fetch historical data for all device entities.
        
        Args:
            device_config: Device configuration with entity IDs
            start_time: Start of historical period
            end_time: End of historical period
            
        Returns:
            HistoricalDataSet combining data from all entities
            
        Raises:
            ValueError: If critical data cannot be fetched
        """
        from ..infrastructure.adapters import (
            ClimateDataAdapter,
            SensorDataAdapter,
            WeatherDataAdapter,
        )

        _LOGGER.info("Fetching historical data for device from %s to %s", start_time, end_time)

        combined_data: dict[HistoricalDataKey, list] = {}

        # Fetch climate data (vtherm - provides indoor temp, target temp, heating state)
        try:
            _LOGGER.debug("Fetching climate data from %s", device_config.vtherm_entity_id)
            climate_adapter = ClimateDataAdapter(self._hass)

            # Fetch indoor temperature (current_temperature attribute)
            indoor_data = await climate_adapter.fetch_historical_data(
                device_config.vtherm_entity_id,
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(indoor_data.data)

            # Fetch target temperature
            target_data = await climate_adapter.fetch_historical_data(
                device_config.vtherm_entity_id,
                HistoricalDataKey.TARGET_TEMP,
                start_time,
                end_time,
            )
            combined_data.update(target_data.data)

            # Fetch heating state (hvac_action or mode)
            heating_state = await climate_adapter.fetch_historical_data(
                device_config.vtherm_entity_id,
                HistoricalDataKey.HEATING_STATE,
                start_time,
                end_time,
            )
            combined_data.update(heating_state.data)
        except Exception as exc:
            _LOGGER.error(
                "Failed to fetch climate data from %s: %s",
                device_config.vtherm_entity_id,
                exc,
            )
            raise ValueError(f"Cannot fetch climate data from {device_config.vtherm_entity_id}") from exc

        # Fetch optional sensor data
        sensor_adapter = SensorDataAdapter(self._hass)

        if device_config.humidity_in_entity_id:
            try:
                _LOGGER.debug("Fetching indoor humidity from %s", device_config.humidity_in_entity_id)
                humidity_in = await sensor_adapter.fetch_historical_data(
                    device_config.humidity_in_entity_id,
                    HistoricalDataKey.INDOOR_HUMIDITY,
                    start_time,
                    end_time,
                )
                combined_data.update(humidity_in.data)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch indoor humidity: %s", exc)

        if device_config.humidity_out_entity_id:
            try:
                _LOGGER.debug("Fetching outdoor humidity from %s", device_config.humidity_out_entity_id)
                humidity_out = await sensor_adapter.fetch_historical_data(
                    device_config.humidity_out_entity_id,
                    HistoricalDataKey.OUTDOOR_HUMIDITY,
                    start_time,
                    end_time,
                )
                combined_data.update(humidity_out.data)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch outdoor humidity: %s", exc)

        # Fetch optional weather data (cloud coverage, outdoor temp)
        if device_config.cloud_cover_entity_id:
            try:
                _LOGGER.debug("Fetching cloud coverage from %s", device_config.cloud_cover_entity_id)
                weather_adapter = WeatherDataAdapter(self._hass)
                cloud_data = await weather_adapter.fetch_historical_data(
                    device_config.cloud_cover_entity_id,
                    HistoricalDataKey.CLOUD_COVERAGE,
                    start_time,
                    end_time,
                )
                combined_data.update(cloud_data.data)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch cloud coverage: %s", exc)

        _LOGGER.debug("Successfully fetched historical data with keys: %s", list(combined_data.keys()))
        return HistoricalDataSet(data=combined_data)
