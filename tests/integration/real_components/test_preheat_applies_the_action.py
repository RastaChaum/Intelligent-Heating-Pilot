"""Every scheduler IHP supports gets the same preheat: the next slot's action, applied early.

Each scenario runs against the real native schedule, HACS Scheduler and Climate Scheduler, with a
real Versatile Thermostat. The scheduler decides what the slot does; IHP only decides how early.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.integration.real_components.home import COMFORT_C, ECO_C, Block, Home
from tests.integration.real_components.schedulers import ALL_SCHEDULERS

MORNING = "07:00"
PAST_DUE_MARGIN = timedelta(minutes=1)


@pytest.fixture(params=ALL_SCHEDULERS, ids=lambda cls: cls.name)
def scheduler(request: pytest.FixtureRequest):
    return request.param()


async def _preheat_for(home: Home, scheduler, block: Block):
    entity = await scheduler.install(home, [block])
    await home.start_ihp([entity], **scheduler.ihp_options)
    await home.settle()
    return entity


@pytest.mark.usefixtures("real_components")
async def test_the_slot_preset_is_applied_at_the_anticipated_start(home: Home, scheduler) -> None:
    await _preheat_for(home, scheduler, Block(MORNING, preset="comfort"))

    anticipated = home.anticipated_start
    assert anticipated is not None
    assert home.now < anticipated < home.at(MORNING)
    assert home.preset == "eco"

    await home.reach_anticipated_start()

    assert home.preset == "comfort"


@pytest.mark.usefixtures("real_components")
async def test_the_slot_temperature_is_applied_at_the_anticipated_start(
    home: Home, scheduler
) -> None:
    await _preheat_for(home, scheduler, Block(MORNING, temperature=COMFORT_C))
    assert home.target == ECO_C

    await home.reach_anticipated_start()

    assert home.target == COMFORT_C


@pytest.mark.usefixtures("real_components")
async def test_nothing_is_applied_before_the_anticipated_start(home: Home, scheduler) -> None:
    await _preheat_for(home, scheduler, Block(MORNING, preset="comfort"))
    anticipated = home.anticipated_start
    assert anticipated is not None
    home.forget_commands()

    await home.advance_to(anticipated - 2 * PAST_DUE_MARGIN)

    assert home.preset == "eco"
    assert home.commands_to_thermostat() == []


@pytest.mark.usefixtures("real_components")
async def test_the_scheduler_taking_over_at_the_slot_changes_nothing(home: Home, scheduler) -> None:
    await _preheat_for(home, scheduler, Block(MORNING, preset="comfort"))
    await home.reach_anticipated_start()

    await home.advance_to(home.at(MORNING) + PAST_DUE_MARGIN)

    assert home.preset == "comfort"
    assert home.target == COMFORT_C


@pytest.mark.usefixtures("real_components")
async def test_nothing_is_applied_while_ihp_preheating_is_off(home: Home, scheduler) -> None:
    await _preheat_for(home, scheduler, Block(MORNING, preset="comfort"))
    await home.turn_ihp_off()
    anticipated = home.anticipated_start

    await home.advance_to((anticipated or home.at(MORNING)) + 2 * PAST_DUE_MARGIN)

    assert home.preset == "eco"
