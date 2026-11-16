"""HAScheduleSlotLookup: the slots around a moment, per kind of scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IPresetTemperatureResolver,
    ISchedulerOwnershipResolver,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    SchedulerKind,
    SlotAction,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_scheduler_reader import (
    HAClimateSchedulerReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader import (
    HANativeScheduleReader,
    NativeScheduleSettings,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.schedule_slot_lookup import (
    HAScheduleSlotLookup,
)

PARIS = ZoneInfo("Europe/Paris")
MOMENT = datetime(2026, 11, 17, 5, 30, tzinfo=PARIS)  # a Tuesday, 05:30
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
TEMPS = {"eco": 18.0, "comfort": 21.0, "boost": 23.0}


class _Kinds(ISchedulerOwnershipResolver):
    def __init__(self, kinds: dict[str, SchedulerKind]) -> None:
        self._kinds = kinds

    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        return self._kinds.get(scheduler_entity_id, SchedulerKind.UNKNOWN)


class _Presets(IPresetTemperatureResolver):
    def resolve(self, preset: str) -> float | None:
        return TEMPS.get(preset)


def _block(start: str, end: str, data: dict | None = None) -> dict:
    block = {"from": f"{start}:00", "to": f"{end}:00"}
    if data is not None:
        block["data"] = data
    return block


def _lookup(
    kinds: dict[str, SchedulerKind],
    states: dict[str, Mock] | None = None,
    blocks: list[dict] | None = None,
    has_service: bool = True,
):
    hass = Mock()
    hass.states.get.side_effect = (states or {}).get
    hass.services.has_service = Mock(return_value=has_service)
    hass.services.async_call = AsyncMock(
        return_value={"schedule.plan": {day: list(blocks or []) for day in WEEKDAYS}}
    )
    native = HANativeScheduleReader(hass, NativeScheduleSettings(drive_enabled=False))
    return HAScheduleSlotLookup(
        hass,
        list(kinds),
        _Kinds(kinds),
        native,
        HAClimateSchedulerReader("climate.vtherm"),
        _Presets(),
    )


@pytest.mark.asyncio
class TestNative:
    kinds = {"schedule.plan": SchedulerKind.NATIVE}

    async def test_the_block_in_effect_and_the_one_that_follows(self) -> None:
        blocks = [
            _block("06:00", "09:00", {"preset": "comfort"}),
            _block("09:00", "22:00", {"preset": "eco"}),
        ]
        around = await _lookup(self.kinds, blocks=blocks).get_slots_around(
            datetime(2026, 11, 17, 8, 0, tzinfo=PARIS)
        )

        assert around.in_effect is not None and around.in_effect.action == SlotAction(
            preset="comfort"
        )
        assert around.in_effect.target_temp == 21.0
        assert around.following is not None and around.following.target_temp == 18.0
        assert around.following.target_time == datetime(2026, 11, 17, 9, 0, tzinfo=PARIS)

    async def test_before_any_block_only_the_following_one_is_known(self) -> None:
        blocks = [_block("07:00", "22:00", {"preset": "boost"})]

        around = await _lookup(self.kinds, blocks=blocks).get_slots_around(MOMENT)

        assert around.in_effect is None
        assert around.following is not None
        assert around.following.target_time == datetime(2026, 11, 17, 7, 0, tzinfo=PARIS)

    async def test_the_actions_are_read_even_when_ihp_does_not_drive_the_schedule(self) -> None:
        around = await _lookup(
            self.kinds, blocks=[_block("07:00", "22:00", {"temperature": 22.5})]
        ).get_slots_around(MOMENT)

        assert around.following is not None
        assert around.following.action == SlotAction(temperature=22.5)

    async def test_a_block_without_the_data_keys_gives_no_slot(self) -> None:
        around = await _lookup(self.kinds, blocks=[_block("07:00", "22:00")]).get_slots_around(
            MOMENT
        )

        assert around.following is None

    async def test_a_block_ending_at_midnight_is_in_effect_until_then(self) -> None:
        around = await _lookup(
            self.kinds, blocks=[_block("18:00", "24:00", {"preset": "comfort"})]
        ).get_slots_around(datetime(2026, 11, 17, 23, 30, tzinfo=PARIS))

        assert around.in_effect is not None

    async def test_without_the_get_schedule_service_nothing_is_known(self) -> None:
        around = await _lookup(
            self.kinds, blocks=[_block("07:00", "22:00", {"preset": "boost"})], has_service=False
        ).get_slots_around(MOMENT)

        assert around.in_effect is None and around.following is None

    async def test_an_unreadable_schedule_gives_nothing(self) -> None:
        lookup = _lookup(self.kinds)
        lookup._native._hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))

        around = await lookup.get_slots_around(MOMENT)

        assert around.in_effect is None and around.following is None

    async def test_a_block_after_the_week_boundary_is_reached(self) -> None:
        """Only Sundays have a block: the following one is found days ahead."""
        hass_blocks = {day: [] for day in WEEKDAYS}
        hass_blocks["sunday"] = [_block("08:00", "20:00", {"preset": "comfort"})]
        lookup = _lookup(self.kinds)
        lookup._native._hass.services.async_call = AsyncMock(
            return_value={"schedule.plan": hass_blocks}
        )

        around = await lookup.get_slots_around(MOMENT)

        assert around.following is not None
        assert around.following.target_time == datetime(2026, 11, 22, 8, 0, tzinfo=PARIS)


def _hacs_state(next_trigger: datetime, preset: str = "comfort", state: str = "waiting") -> Mock:
    return Mock(
        state=state,
        attributes={
            "next_trigger": next_trigger.isoformat(),
            "next_slot": 0,
            "actions": [{"service": "climate.set_preset_mode", "data": {"preset_mode": preset}}],
        },
    )


@pytest.mark.asyncio
class TestHacsScheduler:
    kinds = {"switch.plan": SchedulerKind.HACS}

    async def test_a_next_trigger_after_the_moment_is_the_following_slot(self) -> None:
        trigger = MOMENT + timedelta(hours=1, minutes=30)
        lookup = _lookup(self.kinds, {"switch.plan": _hacs_state(trigger)})

        around = await lookup.get_slots_around(MOMENT)

        assert around.following is not None
        assert around.following.action == SlotAction(preset="comfort")
        assert around.following.target_temp == 21.0
        assert around.in_effect is None  # never guessed

    async def test_a_next_trigger_before_the_moment_says_nothing(self) -> None:
        """Other slots may lie between now and the moment: the next trigger may not be the one."""
        lookup = _lookup(self.kinds, {"switch.plan": _hacs_state(MOMENT - timedelta(hours=2))})

        around = await lookup.get_slots_around(MOMENT)

        assert around.following is None and around.in_effect is None

    async def test_a_disabled_scheduler_says_nothing(self) -> None:
        trigger = MOMENT + timedelta(hours=1)
        lookup = _lookup(self.kinds, {"switch.plan": _hacs_state(trigger, state="off")})

        assert (await lookup.get_slots_around(MOMENT)).following is None

    async def test_a_temperature_action(self) -> None:
        state = Mock(
            state="waiting",
            attributes={
                "next_trigger": (MOMENT + timedelta(hours=1)).isoformat(),
                "next_slot": 0,
                "actions": [{"service": "climate.set_temperature", "data": {"temperature": 22}}],
            },
        )

        around = await _lookup(self.kinds, {"switch.plan": state}).get_slots_around(MOMENT)

        assert around.following is not None
        assert around.following.action == SlotAction(temperature=22.0)

    async def test_an_unreadable_action_gives_no_slot(self) -> None:
        state = Mock(
            state="waiting",
            attributes={"next_trigger": (MOMENT + timedelta(hours=1)).isoformat(), "next_slot": 5},
        )

        assert (
            await _lookup(self.kinds, {"switch.plan": state}).get_slots_around(MOMENT)
        ).following is None

    async def test_a_preset_whose_temperature_is_unknown_gives_no_slot(self) -> None:
        trigger = MOMENT + timedelta(hours=1)
        lookup = _lookup(self.kinds, {"switch.plan": _hacs_state(trigger, preset="party")})

        assert (await lookup.get_slots_around(MOMENT)).following is None


@pytest.mark.asyncio
class TestClimateScheduler:
    kinds = {"switch.cs": SchedulerKind.CLIMATE_SCHEDULER}

    async def test_the_next_node_after_the_moment_is_the_following_slot(self) -> None:
        state = Mock(
            state="on",
            attributes={
                "next_trigger": (MOMENT + timedelta(hours=1)).isoformat(),
                "next_slot": 0,
                "actions": [
                    {
                        "entity_id": "climate.vtherm",
                        "service": "climate.set_preset_mode",
                        "data": {"preset_mode": "boost"},
                    }
                ],
            },
        )

        around = await _lookup(self.kinds, {"switch.cs": state}).get_slots_around(MOMENT)

        assert around.following is not None
        assert around.following.action == SlotAction(preset="boost")
        assert around.in_effect is None


@pytest.mark.asyncio
class TestSeveralSchedulers:
    async def test_the_earliest_following_slot_and_the_latest_in_effect_slot_win(self) -> None:
        kinds = {
            "schedule.plan": SchedulerKind.NATIVE,
            "switch.plan": SchedulerKind.HACS,
        }
        late = MOMENT + timedelta(hours=3)
        early = MOMENT + timedelta(hours=1)
        lookup = _lookup(
            kinds,
            {"switch.plan": _hacs_state(late)},
            blocks=[_block("06:30", "22:00", {"preset": "boost"})],
        )
        around = await lookup.get_slots_around(MOMENT)
        assert around.following is not None
        assert around.following.target_time == early  # the native block at 06:30

    async def test_an_unknown_kind_is_skipped(self) -> None:
        lookup = _lookup(
            {"switch.other": SchedulerKind.UNKNOWN},
            {"switch.other": Mock(state="on", attributes={})},
        )

        around = await lookup.get_slots_around(MOMENT)

        assert around.in_effect is None and around.following is None

    async def test_one_failing_scheduler_does_not_block_the_others(self) -> None:
        kinds = {"switch.broken": SchedulerKind.HACS, "switch.plan": SchedulerKind.HACS}

        def explode(key, default=None):
            if key == "next_trigger":
                raise RuntimeError("boom")
            return default

        broken = Mock(state="waiting")
        broken.attributes = Mock()
        broken.attributes.get = Mock(side_effect=explode)
        lookup = _lookup(
            kinds,
            {"switch.broken": broken, "switch.plan": _hacs_state(MOMENT + timedelta(hours=1))},
        )

        around = await lookup.get_slots_around(MOMENT)

        assert around.following is not None
