"""Tests for HAPreheatRecordStorage: the one preheat record per IHP instance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ClimateSnapshot,
    PreheatRecord,
    SlotAction,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.preheat_record_storage import (
    HAPreheatRecordStorage,
)

STORE = "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
NOW = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)


class FakeStore:
    """In-memory Store that keeps its data across instances, like the real one on disk."""

    disk: dict[str, Any] = {}

    def __init__(self, hass: Any, version: int, key: str) -> None:
        self._key = key

    async def async_load(self) -> Any:
        return FakeStore.disk.get(self._key)

    async def async_save(self, data: Any) -> None:
        FakeStore.disk[self._key] = data


@pytest.fixture(autouse=True)
def fake_disk():
    FakeStore.disk = {}
    with patch(STORE, FakeStore):
        yield


def _record(**overrides) -> PreheatRecord:
    values = {
        "timeslot_id": "switch.plan_2026-11-14T07:00:00+00:00",
        "scheduler_entity": "switch.plan",
        "slot_time": NOW + timedelta(hours=2),
        "previous": ClimateSnapshot("heat", "eco", 18.0, ("eco", "comfort")),
        "applied": SlotAction(preset="comfort", temperature=21.0),
        "recorded_at": NOW,
    }
    values.update(overrides)
    return PreheatRecord(**values)


@pytest.mark.asyncio
async def test_a_new_store_holds_no_record() -> None:
    assert await HAPreheatRecordStorage(Mock(), "entry").load() is None


@pytest.mark.asyncio
async def test_a_saved_record_is_loaded_back_unchanged() -> None:
    storage = HAPreheatRecordStorage(Mock(), "entry")
    await storage.save(_record())

    assert await storage.load() == _record()


@pytest.mark.asyncio
async def test_the_record_survives_a_new_instance() -> None:
    """A restart builds a new adapter: the record must come from the disk."""
    await HAPreheatRecordStorage(Mock(), "entry").save(_record())

    assert await HAPreheatRecordStorage(Mock(), "entry").load() == _record()


@pytest.mark.asyncio
async def test_datetimes_keep_their_timezone() -> None:
    storage = HAPreheatRecordStorage(Mock(), "entry")
    await storage.save(_record())

    loaded = await HAPreheatRecordStorage(Mock(), "entry").load()
    assert loaded is not None
    assert loaded.slot_time.tzinfo is not None
    assert loaded.recorded_at.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_clear_removes_the_record() -> None:
    storage = HAPreheatRecordStorage(Mock(), "entry")
    await storage.save(_record())

    await storage.clear()

    assert await HAPreheatRecordStorage(Mock(), "entry").load() is None


@pytest.mark.asyncio
async def test_a_new_save_replaces_the_previous_record() -> None:
    storage = HAPreheatRecordStorage(Mock(), "entry")
    await storage.save(_record())
    await storage.save(_record(timeslot_id="switch.plan_other"))

    loaded = await storage.load()
    assert loaded is not None and loaded.timeslot_id == "switch.plan_other"


@pytest.mark.asyncio
async def test_each_entry_has_its_own_record() -> None:
    await HAPreheatRecordStorage(Mock(), "entry_a").save(_record())

    assert await HAPreheatRecordStorage(Mock(), "entry_b").load() is None


@pytest.mark.asyncio
async def test_unreadable_data_is_treated_as_no_record() -> None:
    FakeStore.disk["intelligent_heating_pilot_preheat_record_entry"] = {"record": {"junk": 1}}

    assert await HAPreheatRecordStorage(Mock(), "entry").load() is None


@pytest.mark.asyncio
async def test_a_claimed_record_stays_claimed_after_a_restart() -> None:
    from dataclasses import replace

    await HAPreheatRecordStorage(Mock(), "entry").save(replace(_record(), claimed=True))

    loaded = await HAPreheatRecordStorage(Mock(), "entry").load()
    assert loaded is not None and loaded.claimed is True


@pytest.mark.asyncio
async def test_a_record_saved_before_the_claimed_flag_existed_is_not_claimed() -> None:
    storage = HAPreheatRecordStorage(Mock(), "entry")
    await storage.save(_record())
    del FakeStore.disk["intelligent_heating_pilot_preheat_record_entry"]["record"]["claimed"]

    loaded = await HAPreheatRecordStorage(Mock(), "entry").load()
    assert loaded is not None and loaded.claimed is False
