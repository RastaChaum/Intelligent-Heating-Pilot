"""CombinedTimeslotReader: a source whose target comes from the schedule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.slot_sources import (
    CombinedTimeslotReader,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IClimateDataReader,
    IPreheatRecordStore,
    IPresetTemperatureResolver,
    ISchedulerReader,
    IScheduleSlotLookup,
    IWakeUpSourceReader,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ClimateSnapshot,
    PreheatRecord,
    ScheduledTimeslot,
    SlotAction,
    SlotsAround,
    WakeUpReading,
    WakeUpSourceConfig,
)

NOW = datetime(2026, 11, 15, 23, 0, tzinfo=UTC)
ALARM = "sensor.phone_next_alarm"
DEADLINE = NOW + timedelta(hours=6, minutes=30)
PRESETS = ("eco", "comfort", "boost")
TEMPS = {"eco": 18.0, "comfort": 21.0}


def _slot(preset: str, hours: float = 8) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=NOW + timedelta(hours=hours),
        target_temp=TEMPS[preset],
        timeslot_id=f"plan_{preset}",
        scheduler_entity="schedule.plan",
        action=SlotAction(preset=preset),
    )


def _build(
    slots: SlotsAround,
    current_target: float | None = 17.0,
    current_preset: str = "eco",
    record: PreheatRecord | None = None,
    config: WakeUpSourceConfig | None = None,
    with_lookup: bool = True,
):
    scheduler = Mock(spec=ISchedulerReader)
    scheduler.get_next_timeslot = AsyncMock(return_value=None)
    source = Mock(spec=IWakeUpSourceReader)
    source.read = Mock(return_value=WakeUpReading(value=DEADLINE))
    presets = Mock(spec=IPresetTemperatureResolver)
    presets.resolve = Mock(side_effect=TEMPS.get)
    lookup = Mock(spec=IScheduleSlotLookup)
    lookup.get_slots_around = AsyncMock(return_value=slots)
    climate = Mock(spec=IClimateDataReader)
    climate.read_climate_snapshot = Mock(
        return_value=ClimateSnapshot("heat", current_preset, current_target, PRESETS)
    )
    store = Mock(spec=IPreheatRecordStore)
    store.load = AsyncMock(return_value=record)
    config = config or WakeUpSourceConfig(
        ALARM, fixed_target=SlotAction(preset="eco"), target_from_schedule=True
    )
    reader = CombinedTimeslotReader(
        scheduler,
        source,
        [config],
        presets,
        lambda: NOW,
        slot_lookup=lookup if with_lookup else None,
        climate_reader=climate,
        record_store=store,
    )
    return reader, lookup


@pytest.mark.asyncio
async def test_the_target_is_read_from_the_schedule() -> None:
    reader, lookup = _build(SlotsAround(following=_slot("comfort")))

    slot = await reader.get_next_timeslot()

    assert slot is not None
    assert slot.action == SlotAction(preset="comfort")
    assert slot.target_temp == 21.0
    assert slot.target_time == DEADLINE
    lookup.get_slots_around.assert_awaited_once_with(DEADLINE)


@pytest.mark.asyncio
async def test_a_schedule_target_not_higher_than_the_current_one_falls_back_to_the_fixed_one() -> (
    None
):
    reader, _ = _build(SlotsAround(following=_slot("comfort")), current_target=21.0)

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="eco")


@pytest.mark.asyncio
async def test_a_thermostat_in_a_preset_is_compared_through_the_temperature_of_that_preset() -> (
    None
):
    """Versatile Thermostat publishes no requested target while a preset is selected."""
    reader, _ = _build(SlotsAround(following=_slot("comfort")), current_target=None)

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="comfort")


@pytest.mark.asyncio
async def test_a_preset_as_warm_as_the_schedule_target_falls_back_to_the_fixed_one() -> None:
    reader, _ = _build(
        SlotsAround(following=_slot("comfort")), current_target=None, current_preset="comfort"
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="eco")


@pytest.mark.asyncio
async def test_a_preset_whose_temperature_is_unknown_gives_no_reference() -> None:
    reader, _ = _build(
        SlotsAround(following=_slot("comfort")), current_target=None, current_preset="away"
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="eco")


@pytest.mark.asyncio
async def test_the_recorded_earlier_state_in_a_preset_is_compared_through_its_temperature() -> None:
    record = PreheatRecord(
        timeslot_id=f"{ALARM}_2026-11-16",
        scheduler_entity=ALARM,
        slot_time=DEADLINE,
        previous=ClimateSnapshot("heat", "eco", None, PRESETS),
        applied=SlotAction(preset="comfort"),
        recorded_at=NOW,
    )
    reader, _ = _build(
        SlotsAround(following=_slot("comfort")),
        current_target=None,
        current_preset="comfort",
        record=record,
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="comfort")


@pytest.mark.asyncio
async def test_while_a_preheat_runs_the_choice_is_compared_with_the_recorded_earlier_target() -> (
    None
):
    """IHP raised the thermostat to 21: comparing with it would flip the choice mid-preheat."""
    record = PreheatRecord(
        timeslot_id=f"{ALARM}_2026-11-16",
        scheduler_entity=ALARM,
        slot_time=DEADLINE,
        previous=ClimateSnapshot("heat", "eco", 17.0, PRESETS),
        applied=SlotAction(preset="comfort"),
        recorded_at=NOW,
    )
    reader, _ = _build(SlotsAround(following=_slot("comfort")), current_target=21.0, record=record)

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="comfort")


@pytest.mark.asyncio
async def test_a_record_of_another_wake_up_is_not_the_reference() -> None:
    record = PreheatRecord(
        timeslot_id=f"{ALARM}_2026-11-15",
        scheduler_entity=ALARM,
        slot_time=NOW,
        previous=ClimateSnapshot("heat", "eco", 10.0, PRESETS),
        applied=SlotAction(preset="comfort"),
        recorded_at=NOW,
    )
    reader, _ = _build(SlotsAround(following=_slot("comfort")), current_target=21.0, record=record)

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="eco")


@pytest.mark.asyncio
async def test_both_slots_known_the_higher_one_is_used() -> None:
    reader, _ = _build(SlotsAround(in_effect=_slot("comfort", -2), following=_slot("eco")))

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="comfort")


@pytest.mark.asyncio
async def test_a_source_with_no_usable_target_is_ignored() -> None:
    config = WakeUpSourceConfig(ALARM, target_from_schedule=True)
    reader, _ = _build(SlotsAround(), config=config)

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_without_a_lookup_the_fixed_target_applies() -> None:
    reader, _ = _build(SlotsAround(following=_slot("comfort")), with_lookup=False)

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.action == SlotAction(preset="eco")


@pytest.mark.asyncio
async def test_a_fixed_source_never_reads_the_schedule() -> None:
    config = WakeUpSourceConfig(ALARM, fixed_target=SlotAction(preset="eco"))
    reader, lookup = _build(SlotsAround(following=_slot("comfort")), config=config)

    await reader.get_next_timeslot()

    lookup.get_slots_around.assert_not_awaited()
