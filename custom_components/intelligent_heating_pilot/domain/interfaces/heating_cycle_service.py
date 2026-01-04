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
        device_id: str,
        history_data_set: HistoricalDataSet,
        start_time: datetime,
        end_time: datetime,
        cycle_split_duration_minutes: int | None = 0,
    ) -> list[HeatingCycle]:
        """Extract heating cycles from a HistoricalDataSet within a given time range.
        
        Args:
            device_id: The device identifier for the cycles
            history_data_set: A HistoricalDataSet containing all necessary raw sensor data.
            start_time: The start of the time range for cycle extraction.
            end_time: The end of the time range for cycle extraction.
            cycle_split_duration_minutes: Duration in minutes to split long cycles
                into smaller sub-cycles for granular analysis. If 0 or None, no splitting.
            
        Returns:
            A list of HeatingCycle value objects.
        """
        pass