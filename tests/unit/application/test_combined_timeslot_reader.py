"""Unit tests for CombinedTimeslotReader: schedulers and wake-up sources as one next deadline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.slot_sources import (
    CombinedTimeslotReader,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IPresetTemperatureResolver,
    ISchedulerReader,
    IWakeUpSourceReader,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ReadingIssue,
    ScheduledTimeslot,
    SlotAction,
    WakeUpReading,
    WakeUpSourceConfig,
)

NOW = datetime(2026, 11, 15, 23, 0, tzinfo=UTC)
ALARM = "sensor.phone_next_alarm"
SECOND = "input_datetime.arrival"


def _scheduler_slot(at: datetime) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=at,
        target_temp=21.0,
        timeslot_id=f"switch.plan_{at.isoformat()}",
        scheduler_entity="switch.plan",
    )


def _build(
    readings: dict[str, WakeUpReading],
    scheduler_slot: ScheduledTimeslot | None = None,
    sources: list[WakeUpSourceConfig] | None = None,
    preset_temperatures: dict[str, float] | None = None,
):
    scheduler = Mock(spec=ISchedulerReader)
    scheduler.get_next_timeslot = AsyncMock(return_value=scheduler_slot)
    scheduler.get_next_timeslot_of = AsyncMock(return_value=scheduler_slot)
    scheduler.is_scheduler_enabled = AsyncMock(return_value=True)
    source_reader = Mock(spec=IWakeUpSourceReader)
    source_reader.read = Mock(side_effect=lambda entity: readings[entity])
    resolver = Mock(spec=IPresetTemperatureResolver)
    resolver.resolve = Mock(side_effect=lambda preset: (preset_temperatures or {}).get(preset))
    configs = sources or [WakeUpSourceConfig(ALARM, SlotAction(preset="comfort"))]
    reader = CombinedTimeslotReader(scheduler, source_reader, configs, resolver, lambda: NOW)
    return reader, scheduler


@pytest.mark.asyncio
async def test_an_alarm_earlier_than_the_schedule_is_the_next_deadline() -> None:
    alarm = NOW + timedelta(hours=6, minutes=30)
    reader, _ = _build(
        {ALARM: WakeUpReading(value=alarm)},
        _scheduler_slot(NOW + timedelta(hours=8)),
        preset_temperatures={"comfort": 21.0},
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None
    assert slot.target_time == alarm
    assert slot.scheduler_entity == ALARM
    assert slot.action == SlotAction(preset="comfort")
    assert slot.target_temp == 21.0


@pytest.mark.asyncio
async def test_the_schedule_is_the_next_deadline_again_once_the_alarm_has_passed() -> None:
    schedule = _scheduler_slot(NOW + timedelta(hours=8))
    reader, _ = _build({ALARM: WakeUpReading(value=NOW - timedelta(minutes=1))}, schedule)

    assert await reader.get_next_timeslot() is schedule


@pytest.mark.asyncio
async def test_the_schedule_wins_a_tie() -> None:
    at = NOW + timedelta(hours=8)
    schedule = _scheduler_slot(at)
    reader, _ = _build({ALARM: WakeUpReading(value=at)}, schedule)

    assert await reader.get_next_timeslot() is schedule


@pytest.mark.asyncio
async def test_a_later_alarm_leaves_the_schedule_as_the_next_deadline() -> None:
    schedule = _scheduler_slot(NOW + timedelta(hours=8))
    reader, _ = _build({ALARM: WakeUpReading(value=NOW + timedelta(hours=10))}, schedule)

    assert await reader.get_next_timeslot() is schedule


@pytest.mark.asyncio
async def test_without_any_scheduler_the_source_alone_gives_the_deadline() -> None:
    alarm = NOW + timedelta(hours=7)
    reader, _ = _build({ALARM: WakeUpReading(value=alarm)})

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.target_time == alarm


@pytest.mark.asyncio
@pytest.mark.parametrize("issue", list(ReadingIssue))
async def test_a_source_that_gives_no_time_is_skipped(issue: ReadingIssue) -> None:
    reader, _ = _build({ALARM: WakeUpReading(issue=issue)})

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_a_source_beyond_its_horizon_is_skipped() -> None:
    reader, _ = _build({ALARM: WakeUpReading(value=NOW + timedelta(hours=30))})

    assert await reader.get_next_timeslot() is None


@pytest.mark.asyncio
async def test_the_earliest_of_several_sources_wins() -> None:
    early, late = NOW + timedelta(hours=5), NOW + timedelta(hours=9)
    sources = [
        WakeUpSourceConfig(ALARM, SlotAction(preset="comfort")),
        WakeUpSourceConfig(SECOND, SlotAction(temperature=20.0)),
    ]
    reader, _ = _build(
        {ALARM: WakeUpReading(value=late), SECOND: WakeUpReading(value=early)}, sources=sources
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.scheduler_entity == SECOND and slot.target_temp == 20.0


@pytest.mark.asyncio
async def test_an_excluded_source_is_skipped() -> None:
    reader, _ = _build({ALARM: WakeUpReading(value=NOW + timedelta(hours=5))})

    assert await reader.get_next_timeslot(frozenset({ALARM})) is None


@pytest.mark.asyncio
async def test_exclusions_are_forwarded_to_the_schedulers() -> None:
    reader, scheduler = _build({ALARM: WakeUpReading(issue=ReadingIssue.UNKNOWN)})

    await reader.get_next_timeslot(frozenset({"switch.blocked"}))

    scheduler.get_next_timeslot.assert_awaited_once_with(frozenset({"switch.blocked"}))


@pytest.mark.asyncio
async def test_a_preset_target_uses_the_temperature_the_thermostat_publishes() -> None:
    reader, _ = _build(
        {ALARM: WakeUpReading(value=NOW + timedelta(hours=5))},
        preset_temperatures={"comfort": 21.5},
    )

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.target_temp == 21.5


@pytest.mark.asyncio
async def test_an_unpublished_preset_temperature_falls_back_to_a_default() -> None:
    reader, _ = _build({ALARM: WakeUpReading(value=NOW + timedelta(hours=5))})

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.target_temp == 20.0
    assert slot.action == SlotAction(preset="comfort")


@pytest.mark.asyncio
async def test_a_slot_carries_the_hold_of_its_source() -> None:
    hold = timedelta(minutes=90)
    source = WakeUpSourceConfig(ALARM, SlotAction(preset="comfort"), hold=hold)
    reader, _ = _build({ALARM: WakeUpReading(value=NOW + timedelta(hours=5))}, sources=[source])

    slot = await reader.get_next_timeslot()

    assert slot is not None and slot.hold == hold


@pytest.mark.asyncio
async def test_the_slot_id_is_stable_across_a_snooze() -> None:
    """A snooze keeps the wake-up's identity, so a claimed record keeps blocking a new apply."""
    readings = {ALARM: WakeUpReading(value=NOW + timedelta(hours=6))}
    reader, _ = _build(readings)
    first = await reader.get_next_timeslot()
    readings[ALARM] = WakeUpReading(value=NOW + timedelta(hours=6, minutes=10))
    second = await reader.get_next_timeslot()

    assert first is not None and second is not None
    assert first.timeslot_id == second.timeslot_id
    assert first.target_time != second.target_time


@pytest.mark.asyncio
async def test_the_slot_id_changes_with_the_local_day() -> None:
    readings = {ALARM: WakeUpReading(value=NOW + timedelta(hours=6))}
    reader, _ = _build(readings)
    first = await reader.get_next_timeslot()
    readings[ALARM] = WakeUpReading(value=NOW + timedelta(hours=30))
    reader._sources[ALARM] = WakeUpSourceConfig(
        ALARM, SlotAction(preset="comfort"), horizon=timedelta(hours=48)
    )
    second = await reader.get_next_timeslot()

    assert first is not None and second is not None
    assert first.timeslot_id != second.timeslot_id


@pytest.mark.asyncio
async def test_the_next_slot_of_a_source_is_its_own_deadline() -> None:
    alarm = NOW + timedelta(hours=6)
    reader, scheduler = _build(
        {ALARM: WakeUpReading(value=alarm)}, _scheduler_slot(NOW + timedelta(hours=2))
    )

    slot = await reader.get_next_timeslot_of(ALARM)

    assert slot is not None and slot.target_time == alarm
    scheduler.get_next_timeslot_of.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_next_slot_of_a_scheduler_is_delegated() -> None:
    schedule = _scheduler_slot(NOW + timedelta(hours=2))
    reader, scheduler = _build({ALARM: WakeUpReading(issue=ReadingIssue.UNKNOWN)}, schedule)

    assert await reader.get_next_timeslot_of("switch.plan") is schedule
    scheduler.get_next_timeslot_of.assert_awaited_once_with("switch.plan")


@pytest.mark.asyncio
async def test_a_source_is_enabled_while_it_gives_a_valid_deadline() -> None:
    readings = {ALARM: WakeUpReading(value=NOW + timedelta(hours=6))}
    reader, scheduler = _build(readings)

    assert await reader.is_scheduler_enabled(ALARM) is True
    readings[ALARM] = WakeUpReading(issue=ReadingIssue.UNKNOWN)
    assert await reader.is_scheduler_enabled(ALARM) is False
    scheduler.is_scheduler_enabled.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_scheduler_is_enabled_as_its_reader_says() -> None:
    reader, scheduler = _build({ALARM: WakeUpReading(issue=ReadingIssue.UNKNOWN)})
    scheduler.is_scheduler_enabled = AsyncMock(return_value=False)

    assert await reader.is_scheduler_enabled("switch.plan") is False
