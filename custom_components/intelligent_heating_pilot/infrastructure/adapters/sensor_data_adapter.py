"""Sensor data adapter for Home Assistant historical data.

Converts Home Assistant sensor entity history into HistoricalDataSet.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.historical_data_adapter import IHistoricalDataAdapter
from ...domain.value_objects import (
    HistoricalDataSet,
    HistoricalDataKey,
    HistoricalMeasurement,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SensorDataAdapter(IHistoricalDataAdapter):
    """Adapter for converting Home Assistant sensor entity history to HistoricalDataSet.
    
    Sensor entities provide numeric or string state values with optional attributes
    like unit_of_measurement, device_class, etc.
    
    This adapter is generic and can handle any sensor type, mapping them to
    appropriate HistoricalDataKey values based on device_class or configuration.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the sensor data adapter.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        _LOGGER.info("Initialized SensorDataAdapter")

    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for a sensor entity.
        
        Args:
            entity_id: The sensor entity ID (e.g., "sensor.indoor_temperature")
            data_key: The HistoricalDataKey to use (e.g., OUTDOOR_TEMP, INDOOR_HUMIDITY)
            start_time: Start of historical period
            end_time: End of historical period
            
        Returns:
            HistoricalDataSet with extracted sensor data
            
        Raises:
            ValueError: If entity_id is invalid or history cannot be retrieved
        """
        _LOGGER.info(
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
        """Fetch historical data from Home Assistant.
        
        This is a separate method to make it easily mockable in tests.
        
        Args:
            entity_id: The entity ID
            start_time: Start of historical period
            end_time: End of historical period
            
        Returns:
            List of historical records from Home Assistant
        """
        from homeassistant.components.recorder import history
        from functools import partial
        
        # Use Home Assistant's get_significant_states function from recorder
        # Must run in executor to avoid blocking the event loop
        # Use partial to properly pass keyword arguments
        get_states_func = partial(
            history.get_significant_states,
            self._hass,
            start_time,
            end_time,
            entity_ids=[entity_id],
        )
        history_dict = await self._hass.async_add_executor_job(get_states_func)
        
        # Extract records for our entity - returns list of State objects or dicts
        state_list = history_dict.get(entity_id, [])
        
        # Convert State objects to dicts for consistent interface
        result = []
        for state in state_list:
            if isinstance(state, dict):
                # Already a dict
                result.append(state)
            else:
                # State object - convert to dict
                result.append({
                    "entity_id": state.entity_id,
                    "state": state.state,
                    "attributes": state.attributes,
                    "last_changed": state.last_changed,
                    "last_updated": state.last_updated,
                })
        return result
