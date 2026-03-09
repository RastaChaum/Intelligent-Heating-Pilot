"""Home Assistant climate data reader adapter.

Unified adapter combining real-time state reading and historical data access
for VTherm climate entities. Merges the former ClimateDataAdapter (historical)
and HAClimateDataReader (real-time) into a single cohesive adapter.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.climate_data_reader_interface import IClimateDataReader
from ...domain.interfaces.historical_data_adapter_interface import IHistoricalDataAdapter
from ...domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)
from ...domain.value_objects.entity_attribute_mapping import AttributeConcept
from ..vtherm_compat import get_vtherm_attribute
from .entity_attribute_mapper_registry import EntityAttributeMapperRegistry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..recorder_queue import RecorderAccessQueue

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


class HAClimateDataReader(IClimateDataReader, IHistoricalDataAdapter):
    """Unified adapter for VTherm climate data (real-time + historical).

    Combines the responsibilities of:
    - Real-time state reading (IClimateDataReader): entity_id, slope, heating_active
    - Historical data access (IHistoricalDataAdapter): fetch_historical_data

    Uses RecorderAccessQueue (MANDATORY) to serialize database access and prevent
    Home Assistant performance degradation when multiple IHP instances query
    historical data simultaneously.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        recorder_queue: RecorderAccessQueue,
        vtherm_entity_id: str,
    ) -> None:
        """Initialize the climate data reader.

        Args:
            hass: Home Assistant instance
            recorder_queue: Shared FIFO queue to serialize recorder access (MANDATORY)
            vtherm_entity_id: VTherm climate entity ID
                (e.g., ``"climate.living_room_vtherm"``).
        """
        self._hass = hass
        self._recorder_queue = recorder_queue
        self._vtherm_entity_id = vtherm_entity_id
        self._mapper_registry = EntityAttributeMapperRegistry(hass)
        _LOGGER.debug(
            "Initialized HAClimateDataReader for %s with mandatory RecorderAccessQueue",
            vtherm_entity_id,
        )

    # ------------------------------------------------------------------
    # IClimateDataReader implementation (real-time state)
    # ------------------------------------------------------------------

    def get_vtherm_entity_id(self) -> str:
        """Return the VTherm climate entity ID."""
        return self._vtherm_entity_id

    def get_current_slope(self) -> float | None:
        """Get current heating slope from VTherm.

        Reads real-time state (does NOT use RecorderAccessQueue).

        Returns:
            Current slope in °C/h, or ``None`` if not available.
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return None

        slope_raw = get_vtherm_attribute(vtherm_state, "slope")
        if slope_raw is None:
            return None

        try:
            return float(slope_raw)
        except (ValueError, TypeError):
            return None

    def is_heating_active(self) -> bool:
        """Check if heating is currently active.

        Reads real-time state (does NOT use RecorderAccessQueue).

        Heating is active when:
        1. ``hvac_mode == "heat"``
        2. ``current_temperature < target_temperature``

        Returns:
            ``True`` when actively heating, ``False`` otherwise.
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return False

        hvac_mode = vtherm_state.state
        if hvac_mode != "heat":
            return False

        current_temp = get_vtherm_attribute(vtherm_state, "current_temperature")
        target_temp = get_vtherm_attribute(vtherm_state, "temperature")

        if current_temp is None or target_temp is None:
            return False

        try:
            return float(current_temp) < float(target_temp)
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # IHistoricalDataAdapter implementation (historical data)
    # ------------------------------------------------------------------

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

        USES RecorderAccessQueue to serialize database access.

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
            _LOGGER.warning(
                "Cannot fetch historical data for %s: %s. Entity may not exist or may not be configured.",
                entity_id,
                err,
            )
            return HistoricalDataSet(data={})

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
        except asyncio.CancelledError:
            # Shutdown in progress - abort gracefully
            _LOGGER.debug("History fetch cancelled (shutdown in progress) for %s", entity_id)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from None
        except asyncio.TimeoutError:
            # Timeout waiting for database - likely DB is shutdown
            _LOGGER.error("Timeout fetching history for %s (DB may be shutdown)", entity_id)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from None
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

    async def fetch_all_historical_data(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch historical data for all supported keys in a single recorder query.

        Overrides the default implementation to fetch raw history ONCE and extract
        all supported HistoricalDataKey values from the single result, avoiding
        redundant recorder queries.

        Args:
            entity_id: The climate entity ID (e.g., "climate.living_room")
            start_time: Start of historical period
            end_time: End of historical period

        Returns:
            HistoricalDataSet with measurements for all supported data keys

        Raises:
            ValueError: If entity_id is invalid or history cannot be retrieved
        """
        _LOGGER.debug(
            "Fetching all climate history for %s from %s to %s (single recorder query)",
            entity_id,
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

        # Fetch raw history ONCE from the recorder
        try:
            historical_records = await self._fetch_history(entity_id, start_time, end_time)
        except asyncio.CancelledError:
            _LOGGER.debug("History fetch cancelled (shutdown in progress) for %s", entity_id)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching history for %s (DB may be shutdown)", entity_id)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from None
        except Exception as exc:
            _LOGGER.error("Failed to fetch history for %s: %s", entity_id, exc)
            raise ValueError(f"Cannot fetch history for entity {entity_id}") from exc

        if not historical_records:
            _LOGGER.debug("No history found for %s", entity_id)
            return HistoricalDataSet(data={})

        supported_concepts = mapper.get_supported_concepts()
        data: dict[HistoricalDataKey, list[HistoricalMeasurement]] = {}

        # Keys needed by domain services (heating_cycle_service uses these)
        _ESSENTIAL_ATTR_KEYS = {"hvac_action", "hvac_mode"}

        # Extract all supported data keys from the single set of records
        for data_key, concept in DATA_KEY_TO_CONCEPT.items():
            if concept not in supported_concepts:
                continue

            measurements: list[HistoricalMeasurement] = []
            for record in historical_records:
                timestamp = self._parse_timestamp(record)
                full_attributes = record.get("attributes", {})
                entity_id_from_record = record.get("entity_id", entity_id)

                try:
                    value = mapper.extract_attribute_value(full_attributes, concept)
                except ValueError:
                    value = None

                if value is not None:
                    if concept in [
                        AttributeConcept.CURRENT_TEMPERATURE,
                        AttributeConcept.TARGET_TEMPERATURE,
                    ]:
                        value = self._safe_float(value)
                        if value is None:
                            continue

                    # Only keep essential attributes to avoid holding the full
                    # HA State attribute blob in memory (OOM prevention).
                    slim_attributes = {
                        k: full_attributes[k] for k in _ESSENTIAL_ATTR_KEYS if k in full_attributes
                    }

                    measurements.append(
                        HistoricalMeasurement(
                            timestamp=timestamp,
                            value=value,
                            attributes=slim_attributes,
                            entity_id=entity_id_from_record,
                        )
                    )

            if measurements:
                data[data_key] = measurements

        # Release the raw recorder data now that extraction is complete
        del historical_records

        total = sum(len(v) for v in data.values())
        _LOGGER.debug(
            "Extracted %d total measurements for %s across %d keys using %s",
            total,
            entity_id,
            len(data),
            type(mapper).__name__,
        )

        return HistoricalDataSet(data=data)

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

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
        """Fetch historical data from Home Assistant Recorder.

        CRITICAL: Uses RecorderAccessQueue to serialize database access.
        This is a FIFO queue shared across all IHP instances to prevent
        overwhelming the recorder during startup or cache refresh.

        Memory optimization: converts State objects to lightweight dicts
        immediately and releases the original recorder result to prevent
        holding large HA State blobs in memory (OOM prevention for 8+ devices).

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
            _LOGGER.debug("Acquired recorder lock for climate entity %s", entity_id)
            history_dict = await get_instance(self._hass).async_add_executor_job(get_states_func)

        # Extract records for our entity - returns list of State objects or dicts
        state_list = history_dict.get(entity_id, [])
        # Release the full history dict immediately to free memory
        del history_dict

        # Convert State objects to lightweight dicts, keeping only the
        # attributes that downstream code actually needs (hvac_action,
        # hvac_mode, and the mapper-extracted values).  This avoids
        # holding the full HA attribute blob (20-30 keys per VTherm state
        # change) in memory across 8 devices × 7 days of data.
        result = []
        for state in state_list:
            if isinstance(state, dict):
                result.append(state)
            else:
                # Extract only essential attributes from the State object
                raw_attrs = state.attributes
                slim_attrs = {}
                for key in (
                    "hvac_action",
                    "hvac_mode",
                    "current_temperature",
                    "temperature",
                    "humidity",
                ):
                    val = raw_attrs.get(key)
                    if val is not None:
                        slim_attrs[key] = val
                # VTherm specific_states may contain nested data we need
                specific = raw_attrs.get("specific_states")
                if specific is not None:
                    slim_attrs["specific_states"] = specific

                result.append(
                    {
                        "entity_id": state.entity_id,
                        "state": state.state,
                        "attributes": slim_attrs,
                        "last_changed": state.last_changed,
                        "last_updated": state.last_updated,
                    }
                )
        # Release the original state list to free LazyState objects
        del state_list
        return result
