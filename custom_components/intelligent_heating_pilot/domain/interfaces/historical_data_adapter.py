"""Historical data adapter interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects import HistoricalDataKey, HistoricalDataSet


class IHistoricalDataAdapter(ABC):
    """Contract for adapting Home Assistant historical data into HistoricalDataSet.
    
    Implementations of this interface retrieve historical data from Home Assistant
    for different entity types (climate, sensor, weather) and transform them into
    a standardized HistoricalDataSet format.
    """
    
    @abstractmethod
    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for an entity and convert to HistoricalDataSet.
        
        Args:
            entity_id: The Home Assistant entity ID (e.g., "climate.living_room")
            data_key: The HistoricalDataKey to use for categorizing the measurements
            start_time: The start of the historical period
            end_time: The end of the historical period
            
        Returns:
            A HistoricalDataSet containing the fetched and transformed data
            
        Raises:
            ValueError: If entity_id is invalid or data cannot be fetched
        """
        pass
