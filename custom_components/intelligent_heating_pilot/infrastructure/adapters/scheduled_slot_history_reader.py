"""Home Assistant scheduled slot history adapter.

Feeds the slots that came due into cycle extraction, read from the history of
IHP's own Next Schedule Time sensor, so a late preheat can be filed under the
slot it was heating for (#254).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ...const import ATTR_NEXT_TARGET_TEMP, DOMAIN
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

SENSOR_DOMAIN = "sensor"
NEXT_SCHEDULE_UNIQUE_ID_SUFFIX = "_next_schedule_time"


class HAScheduledSlotHistoryReader(IHistoricalDataAdapter):
    """Reads the slots that came due from the Next Schedule Time sensor history.

    The sensor's state is the time of the next slot IHP aims at, and its
    ``next_target_temperature`` attribute the slot's target. Every slot it showed
    came due at that time, so its history lists the slots of every day IHP ran on,
    including those of a fallback scheduler (#64).

    Cycle extraction asks every adapter about the VTherm entity. This adapter is
    bound to the sensor of its IHP device instead: it ignores the requested
    ``entity_id`` and only answers ``SCHEDULED_SLOT``. The sensor is found through
    the entity registry by its unique id, so a renamed sensor is still read.

    The slot history is optional, so a missing sensor or a failed history query
    yields an empty dataset rather than aborting the extraction of the period.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        recorder_queue: RecorderAccessQueue,
        entry_id: str,
    ) -> None:
        """Initialize the reader.

        Args:
            hass: Home Assistant instance
            recorder_queue: Shared FIFO queue to serialize recorder access (MANDATORY)
            entry_id: Config entry id of the IHP device whose sensor is read
        """
        self._hass = hass
        self._recorder_queue = recorder_queue
        self._entry_id = entry_id
        _LOGGER.debug("Initialized scheduled slot history for entry %s", entry_id)

    async def fetch_historical_data(
        self,
        entity_id: str,
        data_key: HistoricalDataKey,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch the slots that came due, with their targets.

        Args:
            entity_id: Ignored; the adapter is bound to the Next Schedule Time sensor
            data_key: Only SCHEDULED_SLOT is answered
            start_time: Start of historical period
            end_time: End of historical period

        Returns:
            HistoricalDataSet with SCHEDULED_SLOT measurements, possibly empty
        """
        if data_key != HistoricalDataKey.SCHEDULED_SLOT:
            return HistoricalDataSet(data={})

        sensor_id = self._resolve_sensor_entity_id()
        if sensor_id is None:
            _LOGGER.debug("No Next Schedule Time sensor registered for entry %s", self._entry_id)
            return HistoricalDataSet(data={})

        try:
            records = await self._fetch_history(sensor_id, start_time, end_time)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # optional source: must not fail the extraction
            _LOGGER.warning("Scheduled slot history unavailable for %s: %s", sensor_id, exc)
            return HistoricalDataSet(data={})

        slots = self._to_slots(sensor_id, records)
        _LOGGER.debug("Read %d scheduled slots from %s", len(slots), sensor_id)
        return HistoricalDataSet(data={data_key: slots} if slots else {})

    async def fetch_all_historical_data(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch the scheduled slots in one query (its only key)."""
        return await self.fetch_historical_data(
            entity_id, HistoricalDataKey.SCHEDULED_SLOT, start_time, end_time
        )

    def _resolve_sensor_entity_id(self) -> str | None:
        """Find the Next Schedule Time sensor of this IHP device."""
        return er.async_get(self._hass).async_get_entity_id(
            SENSOR_DOMAIN, DOMAIN, f"{self._entry_id}{NEXT_SCHEDULE_UNIQUE_ID_SUFFIX}"
        )

    @staticmethod
    def _to_slots(sensor_id: str, records: list[dict[str, Any]]) -> list[HistoricalMeasurement]:
        """Turn recorded states into one measurement per slot.

        States without a slot time (``unknown``, ``unavailable``) or without a numeric
        target are skipped. A slot recorded several times (after a restart) is kept
        once, with its last recorded target.
        """
        slots: dict[datetime, HistoricalMeasurement] = {}
        for record in records:
            slot_time = dt_util.parse_datetime(str(record.get("state")))
            target = _to_float((record.get("attributes") or {}).get(ATTR_NEXT_TARGET_TEMP))
            if slot_time is None or target is None:
                continue
            due = dt_util.as_utc(slot_time)
            slots[due] = HistoricalMeasurement(due, target, {}, sensor_id)
        return sorted(slots.values(), key=lambda slot: slot.timestamp)

    async def _fetch_history(
        self, entity_id: str, start_time: datetime, end_time: datetime
    ) -> list[dict[str, Any]]:
        """Read the sensor's states from the Recorder, through the shared queue.

        Only the state and the target attribute are kept (OOM prevention).
        """
        from homeassistant.components.recorder import get_instance, history

        get_states = partial(
            history.get_significant_states,
            self._hass,
            start_time,
            end_time,
            entity_ids=[entity_id],
        )
        async with self._recorder_queue.lock:
            history_dict = await get_instance(self._hass).async_add_executor_job(get_states)

        return [
            state
            if isinstance(state, dict)
            else {
                "state": state.state,
                "attributes": {ATTR_NEXT_TARGET_TEMP: state.attributes.get(ATTR_NEXT_TARGET_TEMP)},
            }
            for state in history_dict.get(entity_id, [])
        ]


def _to_float(value: Any) -> float | None:
    """Convert a recorded target to float; None if it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
