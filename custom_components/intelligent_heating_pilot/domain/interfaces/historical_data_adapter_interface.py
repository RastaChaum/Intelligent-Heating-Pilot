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

    async def fetch_all_historical_data(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for all supported keys in a single call.

        This default implementation calls fetch_historical_data once per
        HistoricalDataKey, which may result in redundant recorder queries.
        Subclasses should override this method to fetch the raw history once
        and extract all supported keys from that single result.

        Args:
            entity_id: The Home Assistant entity ID (e.g., "climate.living_room")
            start_time: The start of the historical period
            end_time: The end of the historical period

        Returns:
            A HistoricalDataSet containing measurements for all supported keys
        """
        combined_data: dict = {}
        for data_key in HistoricalDataKey:
            result = await self.fetch_historical_data(
                entity_id=entity_id,
                data_key=data_key,
                start_time=start_time,
                end_time=end_time,
            )
            if result and result.data:
                for k, measurements in result.data.items():
                    if measurements:
                        if k not in combined_data:
                            combined_data[k] = []
                        combined_data[k].extend(measurements)
        return HistoricalDataSet(data=combined_data)
