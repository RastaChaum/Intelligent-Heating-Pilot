"""Preheat for a wake-up time given by an entity, with a real thermostat and schedule.

A wake-up source is an entity holding a point in time, such as a phone's next alarm. The earliest
valid deadline among the schedules and the sources wins, and IHP applies the source's target to
the thermostat itself. Times are today's, since the test home starts on a Monday at 05:00.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.intelligent_heating_pilot.const import (
    CONF_WAKE_UP_ENTITY,
    CONF_WAKE_UP_FROM_SCHEDULE,
    CONF_WAKE_UP_HOLD_MINUTES,
    CONF_WAKE_UP_PRESET,
    CONF_WAKE_UP_SOURCES,
)
from tests.integration.real_components.home import Block, Home
from tests.integration.real_components.schedulers import NativeSchedule

SOURCE = "sensor.phone_next_alarm"
ALARM = "07:00"
LATER_ALARM = "07:10"
SCHEDULE_BLOCK = "09:00"
RECALCULATION = timedelta(minutes=2)
HOLD_MINUTES = 90
WARM_ROOM_C = 20.0  # the boost preset (23°C) is then 3°C away, like comfort from 18°C


def _source(**options: object) -> dict[str, object]:
    return {CONF_WAKE_UP_ENTITY: SOURCE, **options}


def _comfort_source(**options: object) -> dict[str, object]:
    return _source(**{CONF_WAKE_UP_PRESET: "comfort", **options})


def _from_schedule(**options: object) -> dict[str, object]:
    return _source(**{CONF_WAKE_UP_FROM_SCHEDULE: True, **options})


async def _set_alarm(home: Home, at: datetime | str | None) -> None:
    """Publish the source the way a phone does: a UTC timestamp, or no alarm."""
    if at is None:
        home.hass.states.async_set(SOURCE, "unknown")
    else:
        moment = home.at(at) if isinstance(at, str) else at
        home.hass.states.async_set(SOURCE, dt_util.as_utc(moment).isoformat())
    await home.advance(RECALCULATION)


async def _start(
    home: Home, sources: list[dict[str, object]], blocks: list[Block] | None = None
) -> None:
    scheduler = NativeSchedule()
    entities = [await scheduler.install(home, blocks)] if blocks is not None else []
    options = scheduler.ihp_options if blocks is not None else {}
    await home.start_ihp(entities, **options, **{CONF_WAKE_UP_SOURCES: sources})
    await home.settle()


def _preset_commands(home: Home) -> list[str]:
    return [
        str(c.data["preset_mode"])
        for c in home.commands_to_thermostat()
        if c.service == "set_preset_mode"
    ]


@pytest.mark.usefixtures("real_components")
async def test_an_alarm_earlier_than_the_schedule_becomes_the_next_deadline(home: Home) -> None:
    await _start(home, [_comfort_source()], [Block(SCHEDULE_BLOCK, preset="boost")])
    await _set_alarm(home, ALARM)

    assert home.next_deadline == home.at(ALARM)
    await home.reach_anticipated_start()

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
async def test_the_schedule_is_the_next_deadline_again_once_the_alarm_has_passed(
    home: Home,
) -> None:
    await _start(home, [_comfort_source()], [Block(SCHEDULE_BLOCK, preset="boost")])
    await _set_alarm(home, home.now - timedelta(minutes=10))

    assert home.next_deadline == home.at(SCHEDULE_BLOCK)


@pytest.mark.usefixtures("real_components")
async def test_a_wake_up_source_drives_the_thermostat_without_any_scheduler(home: Home) -> None:
    await _start(home, [_comfort_source()])
    await _set_alarm(home, ALARM)

    assert home.next_deadline == home.at(ALARM)
    await home.reach_anticipated_start()

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
async def test_the_earlier_state_is_put_back_after_the_hold(home: Home) -> None:
    await _start(home, [_comfort_source(**{CONF_WAKE_UP_HOLD_MINUTES: HOLD_MINUTES})])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()

    await home.advance_to(home.at(ALARM) + timedelta(minutes=1))
    assert home.preset == "comfort"

    await home.advance_to(home.at(ALARM) + timedelta(minutes=HOLD_MINUTES + 1))
    assert home.preset == "eco"


@pytest.mark.usefixtures("real_components")
async def test_a_manual_change_during_the_hold_is_kept(home: Home) -> None:
    await _start(home, [_comfort_source(**{CONF_WAKE_UP_HOLD_MINUTES: HOLD_MINUTES})])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    await home.advance_to(home.at(ALARM) + timedelta(minutes=1))
    await home.user_selects_preset("boost")
    home.forget_commands()

    await home.advance_to(home.at(ALARM) + timedelta(minutes=HOLD_MINUTES + 1))

    assert home.preset == "boost"
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_without_a_hold_the_thermostat_is_left_as_it_is_after_the_wake_up_time(
    home: Home,
) -> None:
    await _start(home, [_comfort_source()])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    home.forget_commands()

    await home.advance_to(home.at(ALARM) + timedelta(minutes=HOLD_MINUTES + 1))

    assert home.preset == "comfort"
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_a_schedule_slot_reached_during_the_hold_ends_it_without_a_restore(
    home: Home,
) -> None:
    hold = {CONF_WAKE_UP_HOLD_MINUTES: 120}
    await _start(home, [_comfort_source(**hold)], [Block("08:00", preset="comfort")])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    home.forget_commands()

    await home.advance_to(home.at(ALARM) + timedelta(minutes=121))

    assert home.preset == "comfort"
    assert "eco" not in _preset_commands(home)


@pytest.mark.usefixtures("real_components")
async def test_the_wake_up_target_is_read_from_the_schedule(home: Home) -> None:
    home.set_room_temperature(WARM_ROOM_C)
    await _start(home, [_from_schedule()], [Block("08:00", preset="boost")])
    await _set_alarm(home, ALARM)

    assert home.next_deadline == home.at(ALARM)
    await home.reach_anticipated_start()

    assert home.preset == "boost"


@pytest.mark.usefixtures("real_components")
async def test_the_wake_up_target_is_never_lower_than_the_slot_already_in_effect(
    home: Home,
) -> None:
    blocks = [Block("04:00", preset="comfort"), Block("09:00", preset="eco")]
    await _start(home, [_from_schedule()], blocks)
    await _set_alarm(home, "08:00")

    await home.reach_anticipated_start()

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
async def test_the_fixed_target_is_the_fallback_when_the_schedule_cannot_tell(
    home: Home,
) -> None:
    await _start(home, [_from_schedule(**{CONF_WAKE_UP_PRESET: "comfort"})], [])
    await _set_alarm(home, ALARM)

    await home.reach_anticipated_start()

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
async def test_a_source_with_no_usable_target_is_ignored(home: Home) -> None:
    await _start(home, [_from_schedule()], [])
    home.forget_commands()
    await _set_alarm(home, ALARM)

    await home.advance_to(home.at(ALARM) + timedelta(minutes=1))

    assert home.next_deadline is None
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_a_snoozed_alarm_moves_the_deadline_without_going_back_and_forth(
    home: Home,
) -> None:
    await _start(home, [_comfort_source()])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    home.forget_commands()

    await _set_alarm(home, LATER_ALARM)

    assert home.next_deadline == home.at(LATER_ALARM)
    assert home.preset == "comfort"
    assert "eco" not in _preset_commands(home)


@pytest.mark.usefixtures("real_components")
async def test_a_snooze_does_not_override_a_manual_change(home: Home) -> None:
    await _start(home, [_comfort_source()])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    await home.user_selects_preset("boost")
    home.forget_commands()

    await _set_alarm(home, LATER_ALARM)

    assert home.preset == "boost"
    assert _preset_commands(home) == []


@pytest.mark.usefixtures("real_components")
async def test_removing_the_alarm_cancels_the_preheat_and_puts_the_thermostat_back(
    home: Home,
) -> None:
    await _start(home, [_comfort_source()])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    assert home.preset == "comfort"

    await _set_alarm(home, None)

    assert home.preset == "eco"


@pytest.mark.usefixtures("real_components")
async def test_a_closer_alarm_takes_over_a_schedule_preheat_without_restoring_in_between(
    home: Home,
) -> None:
    home.set_room_temperature(WARM_ROOM_C)
    await _start(home, [_comfort_source()], [Block(SCHEDULE_BLOCK, preset="boost")])
    await home.reach_anticipated_start()
    assert home.preset == "boost"
    home.forget_commands()

    await _set_alarm(home, "08:00")

    assert home.next_deadline == home.at("08:00")
    assert home.preset == "comfort"
    assert "eco" not in _preset_commands(home)


@pytest.mark.usefixtures("real_components")
async def test_an_unknown_alarm_gives_no_deadline_and_sends_nothing(home: Home) -> None:
    await _start(home, [_comfort_source()])
    home.hass.states.async_set(SOURCE, "unknown")
    home.forget_commands()

    await home.advance(timedelta(hours=3))

    assert home.next_deadline is None
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_a_restart_during_the_hold_still_puts_the_earlier_state_back(home: Home) -> None:
    await _start(home, [_comfort_source(**{CONF_WAKE_UP_HOLD_MINUTES: HOLD_MINUTES})])
    await _set_alarm(home, ALARM)
    await home.reach_anticipated_start()
    await home.advance_to(home.at(ALARM) + timedelta(minutes=1))
    assert home.preset == "comfort"

    await home.restart_ihp()
    await home.advance_to(home.at(ALARM) + timedelta(minutes=HOLD_MINUTES + 1))

    assert home.preset == "eco"
