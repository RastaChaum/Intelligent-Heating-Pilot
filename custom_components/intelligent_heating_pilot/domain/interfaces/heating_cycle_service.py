"""Interface for heating cycle extraction service."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects.heating import HeatingCycle
from ..value_objects.historical_data import HistoricalDataSet


class IHeatingCycleService(ABC):
    """Abstract interface for extracting heating cycles from historical data."""
    
    @abstractmethod
    async def extract_heating_cycles(
        self,
        history_data_set: HistoricalDataSet,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract heating cycles from a HistoricalDataSet within a given time range.
        
        Args:
            history_data_set: A HistoricalDataSet containing all necessary raw sensor data.
            start_time: The start of the time range for cycle extraction.
            end_time: The end of the time range for cycle extraction.
            
        Returns:
            A list of HeatingCycle value objects.
        """
        pass