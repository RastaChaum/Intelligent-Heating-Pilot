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
    async def get_entity_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
        resolution_minutes: int = 5,
    ) -> list[tuple[datetime, Any]]:
        """Get generic entity history within a time range.
        
        This is a generic method that can retrieve history for any entity type
        (temperature sensors, power states, humidity, etc.).
        
        Args:
            entity_id: Entity ID to retrieve history for
            start_time: Start of time range
            end_time: End of time range
            resolution_minutes: Data resolution in minutes
            
        Returns:
            List of (timestamp, value) tuples. Value type depends on entity.
        """
        pass