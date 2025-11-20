"""Interface for reading historical data from Home Assistant database."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects import HeatingCycle


class IHistoricalDataReader(ABC):
    """Contract for reading historical heating data from database.
    
    Implementations of this interface handle database-specific queries
    to extract historical sensor data and reconstruct heating cycles.
    """
    
    @abstractmethod
    async def get_heating_cycles(
        self,
        room_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[HeatingCycle]:
        """Extract and reconstruct heating cycles for a room within a date range.
        
        Args:
            room_id: Identifier for the room/climate entity
            start_date: Start of date range (inclusive)
            end_date: End of date range (exclusive)
            
        Returns:
            List of reconstructed heating cycles with calculated labels.
        """
        pass
    
    @abstractmethod
    async def get_temperature_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, float]]:
        """Get temperature history for a sensor within a time range.
        
        Args:
            entity_id: Sensor entity ID
            start_time: Start of time range
            end_time: End of time range
            resolution_minutes: Data resolution in minutes
            
        Returns:
            List of (timestamp, temperature) tuples.
        """
        pass
    
    @abstractmethod
    async def get_power_state_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[tuple[datetime, bool]]:
        """Get heating power state history within a time range.
        
        Args:
            entity_id: Climate/heater entity ID
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of (timestamp, is_heating) tuples.
        """
        pass
