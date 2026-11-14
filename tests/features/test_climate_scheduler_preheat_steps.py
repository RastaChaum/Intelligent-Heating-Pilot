"""pytest-bdd steps for Climate Scheduler preheating (direct control of the climate).

The whole stack runs for real over a simulated thermostat: see ``tests/native_stack.py``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind
from tests.native_stack import CLIMATE_ID, NativeStack
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot

scenarios("climate_scheduler_preheat.feature")

SWITCH_ID = "switch.living_room_plan"
OTHER_CLIMATE = "climate.bedroom"
NEXT_TRIGGER = "2026-11-16T18:00:00+01:00"


@pytest.fixture
def context() -> dict:
    return {"state": "on", "actions": []}


@given(parsers.parse('the thermostat is in the "{preset}" preset at {temp:f}°C'))
def thermostat_state(context: dict, preset: str, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset=preset, temperature=temp))


@given(parsers.parse('it offers the presets "{a}", "{b}" and "{c}"'))
def thermostat_presets(context: dict, a: str, b: str, c: str) -> None:
    assert context["climate"].snapshot.available_presets == (a, b, c)


def _temperature(entity: str, value: float) -> dict:
    return {
        "entity_id": entity,
        "service": "climate.set_temperature",
        "data": {"temperature": value},
    }


@given(
    parsers.parse("an enabled Climate Scheduler switch whose next node at {time} sets {temp:f}°C")
)
def enabled_temperature_node(context: dict, time: str, temp: float) -> None:
    context["actions"] = [_temperature(CLIMATE_ID, temp)]


@given(
    parsers.parse(
        'an enabled Climate Scheduler switch whose next node at {time} selects the "{preset}" preset'
    )
)
def enabled_preset_node(context: dict, time: str, preset: str) -> None:
    context["actions"] = [
        {
            "entity_id": CLIMATE_ID,
            "service": "climate.set_preset_mode",
            "data": {"preset_mode": preset},
        }
    ]


@given(
    parsers.parse("a disabled Climate Scheduler switch whose next node at {time} sets {temp:f}°C")
)
def disabled_temperature_node(context: dict, time: str, temp: float) -> None:
    context["state"] = "off"
    context["actions"] = [_temperature(CLIMATE_ID, temp)]


@given(
    parsers.parse(
        "an enabled Climate Scheduler switch for two rooms whose next node at {time} sets "
        "{here:f}°C here and {there:f}°C in the other room"
    )
)
def group_node(context: dict, time: str, here: float, there: float) -> None:
    """One node for two rooms: Climate Scheduler lists the other room first."""
    context["actions"] = [_temperature(OTHER_CLIMATE, there), _temperature(CLIMATE_ID, here)]
    context["entry_slot"] = 0


def _stack(context: dict) -> NativeStack:
    stack = NativeStack(
        context["climate"],
        scheduler_id=SWITCH_ID,
        kind=SchedulerKind.CLIMATE_SCHEDULER,
    )
    stack.schedule_state = context["state"]
    stack.scheduler_attributes.update(
        next_trigger=NEXT_TRIGGER,
        next_slot=context.get("entry_slot", 0),
        actions=context["actions"],
    )
    stack.restart()
    return stack


@given("the anticipated start is reached")
@when("the anticipated start is reached")
def anticipated_start_reached(context: dict) -> None:
    stack = _stack(context)
    stack.recalculate()
    context["stack"] = stack
    context["commands_at_start"] = len(stack.service_calls)


@given("the scheduler re-applies its current node after a restart")
def scheduler_reapplies(context: dict) -> None:
    context["climate"].snapshot = replace(
        context["climate"].snapshot, preset="eco", temperature=18.0
    )


@when("IHP recalculates")
def ihp_recalculates(context: dict) -> None:
    context["stack"].recalculate()


@then(parsers.parse("the thermostat target becomes {temp:f}°C"))
def target_becomes(context: dict, temp: float) -> None:
    assert context["climate"].snapshot.temperature == temp


@then(parsers.parse('the thermostat preset becomes "{preset}"'))
def preset_becomes(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset


@then("no command is sent to the thermostat")
def no_command(context: dict) -> None:
    assert context["stack"].service_calls == []


@then("IHP sends no new command")
def no_new_command(context: dict) -> None:
    assert len(context["stack"].service_calls) == context["commands_at_start"]
