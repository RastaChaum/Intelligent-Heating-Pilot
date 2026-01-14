"""Climate data adapter for Home Assistant historical data.

Converts Home Assistant climate entity history into HistoricalDataSet.
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


class ClimateDataAdapter(IHistoricalDataAdapter):
    """Adapter for converting Home Assistant climate entity history to HistoricalDataSet.
    
    Climate entities contain:
    - state: current climate mode (off, heat, cool, etc.)
    - current_temperature: The current measured temperature
    - target_temperature: The desired temperature
    - hvac_action: Current heating/cooling action (heating, cooling, idle, etc.)
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the climate data adapter.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        _LOGGER.debug("Initialized ClimateDataAdapter")

    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for a climate entity.
        
        Args:
            entity_id: The climate entity ID (e.g., "climate.living_room")
            data_key: The HistoricalDataKey to use (typically INDOOR_TEMP, TARGET_TEMP, or HEATING_STATE)
            start_time: Start of historical period
            end_time: End of historical period
            
        Returns:
            HistoricalDataSet with extracted climate data
            
        Raises:
            ValueError: If entity_id is invalid or history cannot be retrieved
        """
        _LOGGER.debug(
            "Fetching climate history for %s from %s to %s",
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
        
        measurements: list[HistoricalMeasurement] = []

        for record in historical_records:
            timestamp = self._parse_timestamp(record)
            attributes = record.get("attributes", {})
            entity_id_from_record = record.get("entity_id", entity_id)

            # Extract data based on requested data_key
            value = None
            if data_key == HistoricalDataKey.INDOOR_TEMP:
                # Extract current (indoor) temperature
                if "current_temperature" in attributes:
                    value = self._safe_float(attributes["current_temperature"])
            
            elif data_key == HistoricalDataKey.TARGET_TEMP:
                # Extract target temperature
                # Try standard climate attribute first, then VTherm specific one
                if "temperature" in attributes:
                    value = self._safe_float(attributes["temperature"])
                elif "target_temperature" in attributes:
                    value = self._safe_float(attributes["target_temperature"])
            
            elif data_key == HistoricalDataKey.HEATING_STATE:
                # Extract heating state (hvac_action)
                if "hvac_action" in attributes:
                    value = attributes["hvac_action"]
            
            else:
                _LOGGER.warning(
                    "Climate adapter does not support data_key %s for entity %s",
                    data_key,
                    entity_id,
                )
                continue

            # Add measurement if value was extracted
            if value is not None:
                measurements.append(
                    HistoricalMeasurement(
                        timestamp=timestamp,
                        value=value,
                        attributes=attributes,
                        entity_id=entity_id_from_record,
                    )
                )

        # Build result
        data: dict[HistoricalDataKey, list[HistoricalMeasurement]] = {}
        if measurements:
            data[data_key] = measurements

        _LOGGER.debug(
            "Extracted %d measurements for %s with key %s",
            len(measurements),
            entity_id,
            data_key,
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
        # Home Assistant provides ISO format string timestamps
        timestamp_str = record.get("last_changed", record.get("last_updated"))
        
        if isinstance(timestamp_str, str):
            # Parse ISO format string (e.g., "2024-01-15T12:00:00+00:00")
            # Remove timezone info for simplicity
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
        from homeassistant.components.recorder import get_instance, history
        from functools import partial
        
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
        history_dict = await get_instance(self._hass).async_add_executor_job(get_states_func)
        
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
