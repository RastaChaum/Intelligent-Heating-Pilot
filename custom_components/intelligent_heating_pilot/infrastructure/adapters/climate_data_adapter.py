"""Climate data adapter for Home Assistant historical data.

Converts Home Assistant climate entity history into HistoricalDataSet,
using flexible attribute mappers to support multiple entity types.
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
from ...domain.value_objects.entity_attribute_mapping import AttributeConcept
from .entity_attribute_mapper_registry import EntityAttributeMapperRegistry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Mapping from HistoricalDataKey to the corresponding domain concept
DATA_KEY_TO_CONCEPT: dict[HistoricalDataKey, AttributeConcept] = {
    HistoricalDataKey.INDOOR_TEMP: AttributeConcept.CURRENT_TEMPERATURE,
    HistoricalDataKey.TARGET_TEMP: AttributeConcept.TARGET_TEMPERATURE,
    HistoricalDataKey.HEATING_STATE: AttributeConcept.HVAC_ACTION,
    HistoricalDataKey.INDOOR_HUMIDITY: AttributeConcept.INDOOR_HUMIDITY,
    HistoricalDataKey.OUTDOOR_TEMP: AttributeConcept.OUTDOOR_TEMPERATURE,
    HistoricalDataKey.OUTDOOR_HUMIDITY: AttributeConcept.OUTDOOR_HUMIDITY,
    HistoricalDataKey.CLOUD_COVERAGE: AttributeConcept.CLOUD_COVERAGE,
}


class ClimateDataAdapter(IHistoricalDataAdapter):
    """Adapter for converting Home Assistant climate entity history to HistoricalDataSet.

    Uses flexible attribute mappers to support multiple entity types (VTherm,
    generic climate entities, etc.) with different attribute structures.

    Instead of hardcoding attribute names, this adapter:
    1. Detects the entity type automatically
    2. Uses the appropriate attribute mapper
    3. Extracts values based on domain concepts
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the climate data adapter.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._mapper_registry = EntityAttributeMapperRegistry(hass)
        _LOGGER.debug("Initialized ClimateDataAdapter with EntityAttributeMapperRegistry")

    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for a climate entity.

        Uses flexible attribute mapping to extract the requested data
        from the entity's attributes, regardless of entity type.

        Args:
            entity_id: The climate entity ID (e.g., "climate.living_room")
            data_key: The HistoricalDataKey to use (INDOOR_TEMP, TARGET_TEMP, HEATING_STATE)
            start_time: Start of historical period
            end_time: End of historical period

        Returns:
            HistoricalDataSet with extracted climate data

        Raises:
            ValueError: If entity_id is invalid or has missing required attributes
        """
        _LOGGER.debug(
            "Fetching climate history for %s (data_key: %s) from %s to %s",
            entity_id,
            data_key.value,
            start_time,
            end_time,
        )

        # Get mapper for this entity
        try:
            mapper = self._mapper_registry.get_mapper_for_entity(entity_id)
            _LOGGER.debug("Using mapper: %s", type(mapper).__name__)
        except ValueError as err:
            _LOGGER.error("Cannot select mapper for %s: %s", entity_id, err)
            raise

        # Map the data_key to a domain concept
        concept = DATA_KEY_TO_CONCEPT.get(data_key)
        if not concept:
            _LOGGER.debug(
                "No concept mapping for data_key %s, skipping",
                data_key.value,
            )
            return HistoricalDataSet(data={})

        # Check if mapper supports this concept before fetching history
        supported_concepts = mapper.get_supported_concepts()
        if concept not in supported_concepts:
            _LOGGER.debug(
                "Mapper %s does not support concept %s for data_key %s, skipping",
                type(mapper).__name__,
                concept.value,
                data_key.value,
            )
            return HistoricalDataSet(data={})

        # Get historical data from Home Assistant
        try:
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

            # Extract value using the flexible mapper
            try:
                value = mapper.extract_attribute_value(attributes, concept)
            except ValueError:
                _LOGGER.debug("Could not extract %s from attributes", concept.value)
                value = None

            # Add measurement if value was extracted
            if value is not None:
                # For float concepts, ensure we have a numeric value
                if concept in [
                    AttributeConcept.CURRENT_TEMPERATURE,
                    AttributeConcept.TARGET_TEMPERATURE,
                ]:
                    value = self._safe_float(value)
                    if value is None:
                        continue

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
            "Extracted %d measurements for %s with key %s using %s",
            len(measurements),
            entity_id,
            data_key.value,
            type(mapper).__name__,
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
                result.append(
                    {
                        "entity_id": state.entity_id,
                        "state": state.state,
                        "attributes": state.attributes,
                        "last_changed": state.last_changed,
                        "last_updated": state.last_updated,
                    }
                )
        return result
