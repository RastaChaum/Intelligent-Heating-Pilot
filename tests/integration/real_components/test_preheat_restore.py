"""A preheat is undone safely, with a real thermostat and a real scheduler.

Direct control records the thermostat's state once, before it acts, keeps that record across a
restart, puts it back only if nobody changed the thermostat meanwhile, and forgets it once the
slot is reached. Removing a block is only scripted on the native schedule: Climate Scheduler
applies the node in force itself whenever its schedule changes, which would hide IHP's restore.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.integration.real_components.home import ECO_C, Block, Home
from tests.integration.real_components.schedulers import ClimateScheduler, NativeSchedule

MORNING = "07:00"
IMMINENT = timedelta(minutes=3)
RECORD_KEY = "intelligent_heating_pilot_preheat_record"
RECALCULATION = timedelta(minutes=2)


async def _preheat_in_progress(home: Home, scheduler) -> None:
    entity = await scheduler.install(home, [Block(MORNING, preset="comfort")])
    await home.start_ihp([entity], **scheduler.ihp_options)
    await home.settle()
    await home.reach_anticipated_start()
    assert home.preset == "comfort"


async def _remove_the_block(home: Home, scheduler) -> None:
    await scheduler.replace(home, [])
    await home.advance(RECALCULATION)


def _recorded(hass_storage: dict) -> bool:
    for key, stored in hass_storage.items():
        if key.startswith(RECORD_KEY) and stored["data"].get("record"):
            return True
    return False


@pytest.mark.usefixtures("real_components")
async def test_removing_the_block_restores_the_earlier_state(home: Home) -> None:
    await _preheat_in_progress(home, scheduler := NativeSchedule())

    await _remove_the_block(home, scheduler)

    assert home.preset == "eco"
    assert home.target == ECO_C


@pytest.mark.usefixtures("real_components")
async def test_a_manual_change_during_the_preheat_is_never_overwritten(home: Home) -> None:
    await _preheat_in_progress(home, scheduler := NativeSchedule())
    await home.user_selects_preset("boost")
    home.forget_commands()

    await _remove_the_block(home, scheduler)

    assert home.preset == "boost"
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_a_thermostat_set_by_hand_goes_back_to_its_temperature(home: Home) -> None:
    await home.user_sets_temperature(19.0)
    await _preheat_in_progress(home, scheduler := NativeSchedule())

    await _remove_the_block(home, scheduler)

    assert home.target == 19.0
    assert home.preset == "none"


@pytest.mark.usefixtures("real_components")
async def test_cancelling_when_the_slot_is_imminent_restores_nothing(home: Home) -> None:
    await _preheat_in_progress(home, scheduler := NativeSchedule())
    await home.advance_to(home.at(MORNING) - IMMINENT)

    await _remove_the_block(home, scheduler)

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
@pytest.mark.parametrize("scheduler_class", [NativeSchedule, ClimateScheduler])
async def test_a_restart_in_the_middle_of_the_preheat_keeps_it_going(
    home: Home, scheduler_class
) -> None:
    await _preheat_in_progress(home, scheduler_class())
    home.forget_commands()

    await home.restart_ihp()
    await home.advance(RECALCULATION)

    assert home.preset == "comfort"
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
@pytest.mark.parametrize("scheduler_class", [NativeSchedule, ClimateScheduler])
async def test_reaching_the_slot_forgets_what_was_recorded(
    home: Home, hass_storage: dict, scheduler_class
) -> None:
    await _preheat_in_progress(home, scheduler_class())
    assert _recorded(hass_storage), "the state before the preheat is recorded"

    await home.advance_to(home.at(MORNING) + RECALCULATION)

    assert home.preset == "comfort"
    assert not _recorded(hass_storage)
