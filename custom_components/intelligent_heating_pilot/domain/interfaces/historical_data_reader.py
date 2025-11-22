"""Interface for reading historical data from Home Assistant database."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..value_objects import HeatingCycle


class IHistoricalDataReader(ABC):
    """Contract for reading historical heating data from database.

    Implementations of this interface handle database-specific queries
    to extract historical sensor data and reconstruct heating cycles.
    """

    @abstractmethod
    async def get_heating_cycles(
        self,
        climate_entity_id: str,
        start_date: datetime,
        end_date: datetime,
        humidity_entity_id: str | None = None,
        outdoor_temp_entity_id: str | None = None,
        outdoor_humidity_entity_id: str | None = None,
        cloud_coverage_entity_id: str | None = None,
    ) -> list[HeatingCycle]:
        """Extract and reconstruct heating cycles for a room within a date range.

        A heating cycle is detected when the thermostat is in "heat" mode
        and room temperature is at least 0.3°C below target temperature.
        The cycle ends when either condition is no longer met.

        Args:
            climate_entity_id: Identifier for the room/climate entity
            start_date: Start of date range (inclusive)
            end_date: End of date range (exclusive)
            humidity_entity_id: Optional indoor humidity sensor entity
            outdoor_temp_entity_id: Optional outdoor temperature sensor entity
            outdoor_humidity_entity_id: Optional outdoor humidity sensor entity
            cloud_coverage_entity_id: Optional cloud coverage sensor entity

        Returns:
            List of reconstructed heating cycles with environmental data.
        """
        pass

    @abstractmethod
    async def get_room_humidity_history(
        self,
        humidity_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical relative humidity (%) for a room.

        Returns:
            List of (timestamp, humidity_percent).
        """
        pass

    @abstractmethod
    async def get_room_temperature_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical indoor temperature (°C) for a room.

        Returns:
            List of (timestamp, temperature_celsius).
        """
        pass

    @abstractmethod
    async def get_radiator_power_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical radiator power level (%) for a room.

        Returns:
            List of (timestamp, power_percent) where 0–100 represents modulation.
        """
        pass

    @abstractmethod
    async def get_room_slopes_history(
        self,
        climate_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical learned heating slopes (°C/min) for a room.

        Returns:
            List of (timestamp, slope_value).
        """
        pass

    @abstractmethod
    async def get_cloud_coverage_history(
        self,
        cloud_coverage_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 15,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical cloud coverage (%) affecting solar gains.

        Returns:
            List of (timestamp, cloud_coverage_percent).
        """
        pass

    @abstractmethod
    async def get_outdoor_temperature_history(
        self,
        outdoor_temperature_entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 15,
    ) -> list[tuple[datetime, float]]:
        """Retrieve historical outdoor temperature (°C).

        Returns:
            List of (timestamp, temperature_celsius).
        """
        pass