"""Historical data adapter interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects import HistoricalDataKey, HistoricalDataSet

_LOGGER = logging.getLogger(__name__)


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
        """Fetch all supported historical data keys in a single operation.

        Default implementation calls fetch_historical_data() for every
        HistoricalDataKey and merges the results.  Subclasses **should** override
        this method to issue a *single* recorder query and extract all supported
        keys in one pass, eliminating redundant SQL round-trips.

        Args:
            entity_id: The Home Assistant entity ID
            start_time: The start of the historical period
            end_time: The end of the historical period

        Returns:
            A HistoricalDataSet containing measurements for all supported keys
        """
        combined_data: dict[HistoricalDataKey, list] = {}
        for key in HistoricalDataKey:
            try:
                result = await self.fetch_historical_data(entity_id, key, start_time, end_time)
                combined_data.update(result.data)
            except ValueError as exc:
                _LOGGER.debug("Skipping key %s for %s: %s", key, entity_id, exc)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Unexpected error fetching key %s for %s: %s", key, entity_id, exc
                )
        return HistoricalDataSet(data=combined_data)
