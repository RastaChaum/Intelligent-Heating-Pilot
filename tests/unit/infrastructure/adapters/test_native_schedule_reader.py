"""Unit tests for HANativeScheduleReader: next block start and slot action from schedule.get_schedule."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import SlotAction
from custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader import (
    HANativeScheduleReader,
    NativeScheduleSettings,
)

MODULE = (
    "custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader"
)
ENTITY = "schedule.heating"
TZ = ZoneInfo("Europe/Paris")
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONDAY_NOON = datetime(2026, 11, 16, 12, 0, tzinfo=TZ)  # 2026-11-16 is a Monday


def _block(start: str, end: str, data: dict | None = None) -> dict:
    block = {"from": start, "to": end}
    if data is not None:
        block["data"] = data
    return block


def _schedule(**by_day: list[dict]) -> dict:
    return {ENTITY: {day: by_day.get(day, []) for day in DAYS}}


def _reader(schedule: dict | Exception, settings: NativeScheduleSettings | None = None):
    hass = Mock()
    if isinstance(schedule, Exception):
        hass.services.async_call = AsyncMock(side_effect=schedule)
    else:
        hass.services.async_call = AsyncMock(return_value=schedule)
    return HANativeScheduleReader(hass, settings or NativeScheduleSettings()), hass


async def _next(reader: HANativeScheduleReader, now: datetime = MONDAY_NOON):
    with patch(f"{MODULE}.dt_util.now", return_value=now):
        return await reader.next_slot(ENTITY)


class TestNextBlockStart:
    @pytest.mark.asyncio
    async def test_the_next_block_start_after_now_is_returned(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("06:00:00", "08:00:00"), _block("18:00:00", "22:00:00")])
        )

        slot = await _next(reader)

        assert slot is not None
        assert slot.start == datetime(2026, 11, 16, 18, 0, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_a_running_block_is_ignored_in_favour_of_the_next_start(self) -> None:
        """The end of the running block is not a start: the next block's start is."""
        reader, _ = _reader(
            _schedule(monday=[_block("10:00:00", "14:00:00"), _block("18:00:00", "22:00:00")])
        )

        slot = await _next(reader)

        assert slot is not None and slot.start.hour == 18

    @pytest.mark.asyncio
    async def test_adjacent_blocks_are_anticipated_even_while_the_first_runs(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("10:00:00", "13:00:00"), _block("13:00:00", "16:00:00")])
        )

        slot = await _next(reader)

        assert slot is not None and slot.start == datetime(2026, 11, 16, 13, 0, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_after_the_last_block_of_the_day_the_next_day_is_used(self) -> None:
        reader, _ = _reader(
            _schedule(
                monday=[_block("06:00:00", "08:00:00")], tuesday=[_block("05:30:00", "08:00:00")]
            )
        )

        slot = await _next(reader)

        assert slot is not None and slot.start == datetime(2026, 11, 17, 5, 30, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_a_block_after_midnight_keeps_its_own_day(self) -> None:
        now = datetime(2026, 11, 15, 23, 0, tzinfo=TZ)  # Sunday 23:00
        reader, _ = _reader(_schedule(monday=[_block("05:00:00", "08:00:00")]))

        slot = await _next(reader, now)

        assert slot is not None and slot.start == datetime(2026, 11, 16, 5, 0, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_a_schedule_only_on_one_weekday_wraps_to_next_week(self) -> None:
        reader, _ = _reader(_schedule(monday=[_block("06:00:00", "08:00:00")]))

        slot = await _next(reader)  # Monday noon, block already over

        assert slot is not None and slot.start == datetime(2026, 11, 23, 6, 0, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_a_schedule_without_blocks_has_no_next_slot(self) -> None:
        reader, _ = _reader(_schedule())

        assert await _next(reader) is None

    @pytest.mark.asyncio
    async def test_a_block_starting_now_is_not_the_next_one(self) -> None:
        reader, _ = _reader(_schedule(monday=[_block("12:00:00", "14:00:00")]))

        slot = await _next(reader)

        assert slot is not None and slot.start.day == 23  # next Monday

    @pytest.mark.asyncio
    async def test_blocks_given_as_time_objects_are_read_like_strings(self) -> None:
        """Called from Python, the service returns real time objects, not text."""
        reader, _ = _reader(_schedule(monday=[_block(time(18, 0), time(22, 0))]))

        slot = await _next(reader)

        assert slot is not None and slot.start == datetime(2026, 11, 16, 18, 0, tzinfo=TZ)

    @pytest.mark.asyncio
    async def test_the_schedule_is_asked_for_with_a_response(self) -> None:
        reader, hass = _reader(_schedule(monday=[_block("18:00:00", "22:00:00")]))

        await _next(reader)

        hass.services.async_call.assert_awaited_once_with(
            "schedule", "get_schedule", {"entity_id": ENTITY}, blocking=True, return_response=True
        )


class TestFailures:
    @pytest.mark.asyncio
    async def test_a_failing_service_gives_no_slot(self) -> None:
        reader, _ = _reader(RuntimeError("boom"))

        assert await _next(reader) is None

    @pytest.mark.asyncio
    async def test_a_response_without_the_entity_gives_no_slot(self) -> None:
        reader, _ = _reader({"schedule.other": {}})

        assert await _next(reader) is None

    @pytest.mark.asyncio
    async def test_a_missing_response_gives_no_slot(self) -> None:
        reader, _ = _reader(None)  # type: ignore[arg-type]

        assert await _next(reader) is None

    @pytest.mark.asyncio
    async def test_a_malformed_block_is_skipped(self) -> None:
        reader, _ = _reader(_schedule(monday=[{"to": "20:00:00"}, _block("18:00:00", "22:00:00")]))

        slot = await _next(reader)

        assert slot is not None and slot.start.hour == 18


class TestSlotAction:
    DRIVING = NativeScheduleSettings(drive_enabled=True)

    @pytest.mark.asyncio
    async def test_without_the_opt_in_no_action_is_read_even_when_the_block_has_data(self) -> None:
        reader, _ = _reader(_schedule(monday=[_block("18:00:00", "22:00:00", {"preset": "boost"})]))

        slot = await _next(reader)

        assert slot is not None and slot.action is None

    @pytest.mark.asyncio
    async def test_a_preset_in_the_block_data_is_the_action(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"preset": "boost"})]), self.DRIVING
        )

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(preset="boost")

    @pytest.mark.asyncio
    async def test_a_temperature_in_the_block_data_is_the_action(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"temperature": 21})]), self.DRIVING
        )

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(temperature=21.0)

    @pytest.mark.asyncio
    async def test_the_preset_wins_and_the_temperature_is_kept_for_the_calculation(self) -> None:
        data = {"preset": "comfort", "temperature": 21.5}
        reader, _ = _reader(_schedule(monday=[_block("18:00:00", "22:00:00", data)]), self.DRIVING)

        slot = await _next(reader)

        assert slot is not None
        assert slot.action == SlotAction(preset="comfort", temperature=21.5)

    @pytest.mark.asyncio
    async def test_a_block_without_a_known_key_gets_the_fallback_preset(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"other": 1})]), self.DRIVING
        )

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(preset="comfort")

    @pytest.mark.asyncio
    async def test_a_block_without_data_gets_the_fallback_preset(self) -> None:
        reader, _ = _reader(_schedule(monday=[_block("18:00:00", "22:00:00")]), self.DRIVING)

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(preset="comfort")

    @pytest.mark.asyncio
    async def test_the_keys_and_the_fallback_preset_are_configurable(self) -> None:
        settings = NativeScheduleSettings(
            drive_enabled=True, preset_key="mode", temperature_key="target", fallback_preset="eco"
        )
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"mode": "boost"})]), settings
        )
        slot = await _next(reader)
        assert slot is not None and slot.action == SlotAction(preset="boost")

        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"target": 20.0})]), settings
        )
        slot = await _next(reader)
        assert slot is not None and slot.action == SlotAction(temperature=20.0)

        reader, _ = _reader(_schedule(monday=[_block("18:00:00", "22:00:00")]), settings)
        slot = await _next(reader)
        assert slot is not None and slot.action == SlotAction(preset="eco")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "data",
        [
            {"preset": 5},
            {"preset": ""},
            {"preset": "  "},
            {"preset": None},
            {"preset": True},
        ],
    )
    async def test_a_preset_of_the_wrong_type_is_ignored(self, data) -> None:
        reader, _ = _reader(_schedule(monday=[_block("18:00:00", "22:00:00", data)]), self.DRIVING)

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(preset="comfort")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["warm", True, False, None, float("nan"), float("inf")])
    async def test_a_temperature_of_the_wrong_type_is_ignored(self, value) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"temperature": value})]), self.DRIVING
        )

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(preset="comfort")

    @pytest.mark.asyncio
    async def test_a_numeric_string_temperature_is_accepted(self) -> None:
        reader, _ = _reader(
            _schedule(monday=[_block("18:00:00", "22:00:00", {"temperature": "20.5"})]),
            self.DRIVING,
        )

        slot = await _next(reader)

        assert slot is not None and slot.action == SlotAction(temperature=20.5)

    def test_blank_keys_or_fallback_are_rejected(self) -> None:
        for field in ("preset_key", "temperature_key", "fallback_preset"):
            with pytest.raises(ValueError, match=field):
                NativeScheduleSettings(**{field: ""})
