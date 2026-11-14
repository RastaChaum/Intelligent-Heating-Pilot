"""Home Assistant storage adapter for the preheat record.

Implements IPreheatRecordStore on the same Store pattern as the learning caches. The record
is what lets IHP undo a preheat after a restart, so it is written through on every change.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...domain.interfaces.preheat_record_store_interface import IPreheatRecordStore
from ...domain.value_objects.climate_snapshot import ClimateSnapshot
from ...domain.value_objects.preheat_record import PreheatRecord
from ...domain.value_objects.slot_action import SlotAction
from .base_ha_storage import BaseHAStorageAdapter

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "intelligent_heating_pilot_preheat_record"
RECORD_FIELD = "record"


class HAPreheatRecordStorage(BaseHAStorageAdapter[dict[str, Any]], IPreheatRecordStore):
    """Persists the single preheat record of one IHP instance."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the storage.

        Args:
            hass: Home Assistant instance.
            entry_id: Config entry id that scopes the stored file.
        """
        super().__init__(hass=hass, entry_id=entry_id, storage_key=STORAGE_KEY)

    def _get_default_data(self) -> dict[str, Any]:
        """Return the empty storage: no record."""
        return {RECORD_FIELD: None}

    async def load(self) -> PreheatRecord | None:
        """Return the stored record, or None when there is none or it is unreadable."""
        await self._ensure_loaded()
        raw = self._data.get(RECORD_FIELD)
        if raw is None:
            return None
        try:
            return self._deserialize(raw)
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning("Ignoring an unreadable preheat record: %s", raw, exc_info=True)
            return None

    async def save(self, record: PreheatRecord) -> None:
        """Store the record, replacing any earlier one.

        Args:
            record: The record to keep.
        """
        await self._ensure_loaded()
        self._data[RECORD_FIELD] = self._serialize(record)
        await self._save_data()

    async def clear(self) -> None:
        """Remove the stored record, if any."""
        await self._ensure_loaded()
        self._data[RECORD_FIELD] = None
        await self._save_data()

    def _serialize(self, record: PreheatRecord) -> dict[str, Any]:
        return {
            "timeslot_id": record.timeslot_id,
            "scheduler_entity": record.scheduler_entity,
            "slot_time": self._serialize_datetime(record.slot_time),
            "recorded_at": self._serialize_datetime(record.recorded_at),
            "previous": {
                "hvac_mode": record.previous.hvac_mode,
                "preset": record.previous.preset,
                "temperature": record.previous.temperature,
                "available_presets": list(record.previous.available_presets),
            },
            "applied": {"preset": record.applied.preset, "temperature": record.applied.temperature},
        }

    def _deserialize(self, raw: dict[str, Any]) -> PreheatRecord:
        previous = raw["previous"]
        applied = raw["applied"]
        return PreheatRecord(
            timeslot_id=raw["timeslot_id"],
            scheduler_entity=raw["scheduler_entity"],
            slot_time=self._parse_datetime(raw["slot_time"]),
            recorded_at=self._parse_datetime(raw["recorded_at"]),
            previous=ClimateSnapshot(
                hvac_mode=previous["hvac_mode"],
                preset=previous.get("preset"),
                temperature=previous.get("temperature"),
                available_presets=tuple(previous.get("available_presets", ())),
            ),
            applied=SlotAction(
                preset=applied.get("preset"), temperature=applied.get("temperature")
            ),
        )
