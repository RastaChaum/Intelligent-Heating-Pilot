"""Tests for HAScheduledSlotHistoryReader adapter (#254)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import HistoricalDataKey
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    scheduled_slot_history_reader as reader_module,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduled_slot_history_reader import (
    HAScheduledSlotHistoryReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

ENTRY_ID = "entry123"
SENSOR = "sensor.living_room_next_schedule_time"
START = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 2, 0, 0, tzinfo=UTC)
KEY = HistoricalDataKey.SCHEDULED_SLOT


def _record(state: str, target: Any = 20.0) -> dict[str, Any]:
    attributes = {} if target is None else {"next_target_temperature": target}
    return {"state": state, "attributes": attributes}


def _reader(records: list[dict[str, Any]], sensor: str | None = SENSOR) -> tuple:
    registry = MagicMock()
    registry.async_get_entity_id.return_value = sensor
    reader = HAScheduledSlotHistoryReader(MagicMock(), RecorderAccessQueue(), ENTRY_ID)
    fetch = AsyncMock(return_value=records)
    reader._fetch_history = fetch  # type: ignore[method-assign]
    return reader, fetch, registry


async def _slots(reader: HAScheduledSlotHistoryReader, registry: MagicMock) -> list:
    with patch.object(reader_module.er, "async_get", return_value=registry):
        result = await reader.fetch_all_historical_data("climate.living_room", START, END)
    return result.data.get(KEY, [])


@pytest.mark.asyncio
async def test_each_recorded_slot_becomes_a_slot_with_its_target() -> None:
    reader, _, registry = _reader([_record("2026-11-01T08:45:00+01:00", 20.0)])

    slots = await _slots(reader, registry)

    assert [(slot.timestamp, slot.value) for slot in slots] == [
        (datetime(2026, 11, 1, 7, 45, tzinfo=UTC), 20.0)
    ]


@pytest.mark.asyncio
async def test_next_schedule_sensor_is_queried_not_the_requested_entity() -> None:
    """Extraction asks about the VTherm; the Next Schedule Time sensor is what gets read."""
    reader, fetch, registry = _reader([])

    await _slots(reader, registry)

    registry.async_get_entity_id.assert_called_once_with(
        "sensor", "intelligent_heating_pilot", f"{ENTRY_ID}_next_schedule_time"
    )
    assert fetch.call_args.args[0] == SENSOR


@pytest.mark.asyncio
async def test_slot_recorded_several_times_is_one_slot() -> None:
    """After a restart the sensor records the same slot again."""
    records = [
        _record("2026-11-01T08:45:00+00:00"),
        _record("unavailable", None),
        _record("2026-11-01T08:45:00+00:00"),
    ]
    reader, _, registry = _reader(records)

    assert len(await _slots(reader, registry)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record",
    [
        _record("unknown"),
        _record("unavailable"),
        _record("2026-11-01T08:45:00+00:00", None),
        _record("2026-11-01T08:45:00+00:00", "n/a"),
    ],
)
async def test_states_without_a_slot_time_or_target_are_skipped(record: dict) -> None:
    reader, _, registry = _reader([record])

    assert await _slots(reader, registry) == []


@pytest.mark.asyncio
async def test_unregistered_sensor_gives_no_slot() -> None:
    reader, fetch, registry = _reader([], sensor=None)

    assert await _slots(reader, registry) == []
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_history_read_failure_gives_no_slot() -> None:
    """The slot history is optional: it must not fail the extraction of the period."""
    reader, fetch, registry = _reader([])
    fetch.side_effect = RuntimeError("database is gone")

    assert await _slots(reader, registry) == []


@pytest.mark.asyncio
async def test_other_keys_are_not_answered() -> None:
    reader, fetch, _ = _reader([_record("2026-11-01T08:45:00+00:00")])

    result = await reader.fetch_historical_data(
        "climate.living_room", HistoricalDataKey.INDOOR_TEMP, START, END
    )

    assert result.data == {}
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_is_not_absorbed() -> None:
    """A cancelled extraction must not mark its period explored (#187)."""
    reader, fetch, registry = _reader([])
    fetch.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _slots(reader, registry)
