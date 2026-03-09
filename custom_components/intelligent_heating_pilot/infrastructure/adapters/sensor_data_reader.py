"""Home Assistant sensor data reader adapter.

Provides historical data access for sensor entities via HA Recorder.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.historical_data_adapter_interface import IHistoricalDataAdapter
from ...domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..recorder_queue import RecorderAccessQueue

_LOGGER = logging.getLogger(__name__)


class HASensorDataReader(IHistoricalDataAdapter):
    """Adapter for reading historical sensor data from Home Assistant.

    Generic adapter supporting any sensor type (temperature, humidity, etc.)
    mapped to appropriate HistoricalDataKey values.

    Uses RecorderAccessQueue (MANDATORY) to serialize database access and prevent
    Home Assistant performance degradation when multiple IHP instances query
    historical data simultaneously.
    """

    def __init__(self, hass: HomeAssistant, recorder_queue: RecorderAccessQueue) -> None:
        """Initialize the sensor data reader.

        Args:
            hass: Home Assistant instance
            recorder_queue: Shared FIFO queue to serialize recorder access (MANDATORY)
        """
        self._hass = hass
        self._recorder_queue = recorder_queue
        _LOGGER.debug("Initialized HASensorDataReader with mandatory RecorderAccessQueue")

    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for a sensor entity.

        USES RecorderAccessQueue to serialize database access.

        Args:
            entity_id: Sensor entity ID (e.g., "sensor.indoor_temperature")
            data_key: HistoricalDataKey (e.g., OUTDOOR_TEMP, INDOOR_HUMIDITY)
            start_time: Start of historical period
            end_time: End of historical period

        Returns:
            HistoricalDataSet with extracted sensor data

        Raises:
            ValueError: If entity_id is invalid or history cannot be retrieved
        """
        _LOGGER.debug(
            "Fetching sensor history for %s from %s to %s",
            entity_id,
            start_time,
            end_time,
        )

        try:
            # Get historical data from Home Assistant
            historical_records = await self._fetch_history(
                entity_id,
                start_time,
                end_time,
            )
        except Exception as exc:
            _LOGGER.error("Failed to fetch history for %s: %s", entity_id, exc)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from exc

        if not historical_records:
            _LOGGER.warning("No history found for %s", entity_id)
            return HistoricalDataSet(data={})

        # Use the provided data_key to categorize measurements
        measurements: list[HistoricalMeasurement] = []

        for record in historical_records:
            timestamp = self._parse_timestamp(record)
            state = record.get("state")
            attributes = record.get("attributes", {})
            entity_id_from_record = record.get("entity_id", entity_id)

            # Try to convert state to numeric value - skip if not convertible
            numeric_value = self._safe_float(state)
            if numeric_value is None:
                _LOGGER.debug(
                    "Skipping non-numeric sensor state '%s' for %s at %s",
                    state,
                    entity_id,
                    timestamp,
                )
                continue

            measurements.append(
                HistoricalMeasurement(
                    timestamp=timestamp,
                    value=numeric_value,
                    attributes=attributes,
                    entity_id=entity_id_from_record,
                )
            )

        # Build result
        data: dict[HistoricalDataKey, list[HistoricalMeasurement]] = {}

        if measurements:
            data[data_key] = measurements

        _LOGGER.debug(
            "Extracted %d sensor measurements for %s",
            len(measurements),
            entity_id,
        )

        return HistoricalDataSet(data=data)

    @staticmethod
    def _parse_timestamp(record: dict[str, Any]) -> datetime:
        """Parse timestamp from history record.

        Args:
            record: Historical record from Home Assistant

        Returns:
            Parsed datetime object
        """
        timestamp_str = record.get("last_changed", record.get("last_updated"))

        if isinstance(timestamp_str, str):
            # Parse ISO format string
            if "+" in timestamp_str:
                timestamp_str = timestamp_str.split("+")[0]
            elif "Z" in timestamp_str:
                timestamp_str = timestamp_str.replace("Z", "")

            return datetime.fromisoformat(timestamp_str)

        # If already a datetime, return as-is
        if isinstance(timestamp_str, datetime):
            return timestamp_str

        # Fallback: return current time if no timestamp found
        return datetime.now()

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Safely convert value to float.

        Args:
            value: Value to convert

        Returns:
            Float value or None if conversion fails
        """
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def _fetch_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch historical data from Home Assistant Recorder.

        CRITICAL: Uses RecorderAccessQueue to serialize database access.
        This is a FIFO queue shared across all IHP instances to prevent
        overwhelming the recorder during startup or cache refresh.

        Args:
            entity_id: The entity ID
            start_time: Start of historical period
            end_time: End of historical period

        Returns:
            List of historical records from Home Assistant
        """
        from functools import partial

        from homeassistant.components.recorder import get_instance, history

        # Use Home Assistant's get_significant_states function from recorder
        # Must run in recorder executor to avoid blocking and comply with HA best practices
        # Use partial to properly pass keyword arguments
        get_states_func = partial(
            history.get_significant_states,
            self._hass,
            start_time,
            end_time,
            entity_ids=[entity_id],
        )

        # Serialize recorder access via shared FIFO queue (MANDATORY)
        async with self._recorder_queue.lock:
            _LOGGER.debug("Acquired recorder lock for sensor entity %s", entity_id)
            history_dict = await get_instance(self._hass).async_add_executor_job(get_states_func)

        # Extract records for our entity - returns list of State objects or dicts
        state_list = history_dict.get(entity_id, [])
        del history_dict

        # Convert State objects to lightweight dicts (OOM prevention).
        # Sensors typically only have a state value, minimal attributes needed.
        result = []
        for state in state_list:
            if isinstance(state, dict):
                result.append(state)
            else:
                result.append(
                    {
                        "entity_id": state.entity_id,
                        "state": state.state,
                        "attributes": {},
                        "last_changed": state.last_changed,
                        "last_updated": state.last_updated,
                    }
                )
        del state_list
        return result
