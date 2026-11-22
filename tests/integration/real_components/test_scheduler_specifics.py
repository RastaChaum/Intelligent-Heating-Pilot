"""What differs from one scheduler to the next, with the real integrations.

Native schedules are driven on opt-in and read the action from each block's data; HACS Scheduler
keeps its own conditions in charge; Climate Scheduler is driven directly and may be disabled.
"""

from __future__ import annotations

import pytest

from custom_components.intelligent_heating_pilot.const import (
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
)
from tests.integration.real_components.home import BOOST_C, Block, Home
from tests.integration.real_components.schedulers import (
    ClimateScheduler,
    HacsScheduler,
    NativeSchedule,
)

MORNING = "07:00"
LATE_MORNING = "09:00"
OCCUPANCY = "binary_sensor.home_occupied"


async def _preheat_for(home: Home, scheduler, *blocks: Block):
    entity = await scheduler.install(home, list(blocks))
    await home.start_ihp([entity], **scheduler.ihp_options)
    await home.settle()
    return entity


class TestNativeSchedule:
    @pytest.mark.usefixtures("real_components")
    async def test_a_block_without_data_gets_the_fallback_preset(self, home: Home) -> None:
        await _preheat_for(home, NativeSchedule(), Block(MORNING))

        await home.reach_anticipated_start()

        assert home.preset == "comfort"

    @pytest.mark.usefixtures("real_components")
    async def test_the_fallback_preset_is_the_one_the_user_chose(self, home: Home) -> None:
        # Boost is 23°C: from a 20°C room it is the same 3°C of heating as the comfort preset
        home.set_room_temperature(20.0)
        scheduler = NativeSchedule(**{CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: "boost"})
        await _preheat_for(home, scheduler, Block(LATE_MORNING))

        await home.reach_anticipated_start()

        assert home.preset == "boost"

    @pytest.mark.usefixtures("real_components")
    async def test_the_preset_wins_when_the_block_holds_both(self, home: Home) -> None:
        await _preheat_for(
            home, NativeSchedule(), Block(LATE_MORNING, preset="boost", temperature=19.0)
        )
        home.forget_commands()

        await home.reach_anticipated_start()

        assert home.preset == "boost"
        assert [c.service for c in home.commands_to_thermostat()] == ["set_preset_mode"]

    @pytest.mark.usefixtures("real_components")
    async def test_the_keys_of_the_block_data_are_the_ones_the_user_chose(self, home: Home) -> None:
        scheduler = NativeSchedule(**{CONF_NATIVE_SCHEDULE_PRESET_KEY: "mode"})
        await _preheat_for(home, scheduler, Block(MORNING, data={"mode": "comfort"}))

        await home.reach_anticipated_start()

        assert home.preset == "comfort"

    @pytest.mark.usefixtures("real_components")
    async def test_nothing_is_applied_without_the_opt_in(self, home: Home) -> None:
        entity = await NativeSchedule().install(home, [Block(MORNING, preset="comfort")])
        await home.start_ihp([entity])
        await home.settle()
        anticipated = home.anticipated_start
        assert anticipated is not None, "the start is still computed without the opt-in"
        home.forget_commands()

        await home.reach_anticipated_start()

        assert home.preset == "eco"
        assert home.commands_to_thermostat() == []

    @pytest.mark.usefixtures("real_components")
    async def test_a_block_that_follows_a_running_one_is_anticipated_with_its_own_action(
        self, home: Home
    ) -> None:
        await _preheat_for(
            home,
            NativeSchedule(),
            Block("04:00", preset="eco"),
            Block(MORNING, preset="comfort"),
        )
        anticipated = home.anticipated_start
        assert anticipated is not None and home.now < anticipated < home.at(MORNING)

        await home.reach_anticipated_start()

        assert home.preset == "comfort"


class TestHacsScheduler:
    @pytest.mark.usefixtures("real_components")
    async def test_the_scheduler_conditions_are_never_bypassed(self, home: Home) -> None:
        home.hass.states.async_set(OCCUPANCY, "off")
        scheduler = HacsScheduler()
        conditions = [{"entity_id": OCCUPANCY, "value": "on", "match_type": "is"}]
        entity = await scheduler.install(
            home, [Block(MORNING, preset="comfort")], conditions=conditions
        )
        await home.start_ihp([entity])
        await home.settle()

        await home.reach_anticipated_start()

        assert home.preset == "eco"

    @pytest.mark.usefixtures("real_components")
    async def test_the_action_runs_when_the_scheduler_conditions_hold(self, home: Home) -> None:
        home.hass.states.async_set(OCCUPANCY, "on")
        scheduler = HacsScheduler()
        conditions = [{"entity_id": OCCUPANCY, "value": "on", "match_type": "is"}]
        entity = await scheduler.install(
            home, [Block(MORNING, preset="comfort")], conditions=conditions
        )
        await home.start_ihp([entity])
        await home.settle()

        await home.reach_anticipated_start()

        assert home.preset == "comfort"

    @pytest.mark.usefixtures("real_components")
    async def test_the_scheduler_applies_its_own_action_through_run_action(
        self, home: Home
    ) -> None:
        """IHP only triggers the slot: the action the thermostat gets is the scheduler's own."""
        entity = await HacsScheduler().install(home, [Block(MORNING, preset="comfort")])
        await home.start_ihp([entity])
        await home.settle()
        home.forget_commands()

        await home.reach_anticipated_start()

        assert {c.service for c in home.commands_to_thermostat()} == {"set_preset_mode"}
        assert home.preset == "comfort"


class TestClimateScheduler:
    @pytest.mark.usefixtures("real_components")
    async def test_a_disabled_switch_is_never_applied(self, home: Home) -> None:
        scheduler = ClimateScheduler()
        entity = await scheduler.install(home, [Block(MORNING, preset="comfort")])
        await home.hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity}, blocking=True
        )
        await home.start_ihp([entity])
        await home.settle()
        home.forget_commands()

        await home.advance_to(home.at("06:55"))

        assert home.preset == "eco"
        assert home.commands_to_thermostat() == []

    @pytest.mark.usefixtures("real_components")
    async def test_a_temperature_node_is_applied_as_a_temperature(self, home: Home) -> None:
        entity = await ClimateScheduler().install(home, [Block(MORNING, temperature=BOOST_C - 2)])
        await home.start_ihp([entity])
        await home.settle()
        home.forget_commands()

        await home.reach_anticipated_start()

        assert home.target == BOOST_C - 2
        assert [c.service for c in home.commands_to_thermostat()] == ["set_temperature"]
