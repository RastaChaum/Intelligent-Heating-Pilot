"""pytest-bdd steps for ha-chauffage preheating (direct control of the climate).

The whole stack runs for real over a simulated thermostat: see ``tests/native_stack.py``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.value_objects import SchedulerKind
from tests.native_stack import NativeStack
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot

scenarios("chauffage_preheat.feature")

SENSOR_ID = "sensor.living_room_next_change"
NEXT_CHANGE = "2026-11-16T18:00:00+01:00"


@pytest.fixture
def context() -> dict:
    return {"state": NEXT_CHANGE, "attributes": {}}


@given(parsers.parse('the thermostat is in the "{preset}" preset at {temp:f}°C'))
def thermostat_state(context: dict, preset: str, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset=preset, temperature=temp))


@given(parsers.parse('it offers the presets "{a}", "{b}" and "{c}"'))
def thermostat_presets(context: dict, a: str, b: str, c: str) -> None:
    assert context["climate"].snapshot.available_presets == (a, b, c)


@given(
    parsers.parse(
        'a ha-chauffage sensor whose next change at {time} is the "{preset}" preset in {mode} mode'
    )
)
def preset_change(context: dict, time: str, preset: str, mode: str) -> None:
    context["attributes"] = {"hvac_mode": mode, "preset_mode": preset, "temperature": None}


@given(
    parsers.parse("a ha-chauffage sensor whose next change at {time} is {temp:f}°C in {mode} mode")
)
def temperature_change(context: dict, time: str, temp: float, mode: str) -> None:
    context["attributes"] = {"hvac_mode": mode, "preset_mode": None, "temperature": temp}


@given("a ha-chauffage sensor with no next change")
def no_next_change(context: dict) -> None:
    context["state"] = "unknown"


def _stack(context: dict) -> NativeStack:
    stack = NativeStack(context["climate"], scheduler_id=SENSOR_ID, kind=SchedulerKind.CHAUFFAGE)
    stack.schedule_state = context["state"]
    stack.scheduler_attributes.update(context["attributes"])
    stack.restart()
    return stack


@given("the anticipated start is reached")
@when("the anticipated start is reached")
def anticipated_start_reached(context: dict) -> None:
    stack = _stack(context)
    stack.recalculate()
    context["stack"] = stack
    context["commands_at_start"] = len(stack.service_calls)


@given("ha-chauffage applies its change at the slot time")
def chauffage_applies(context: dict) -> None:
    context["climate"].snapshot = replace(context["climate"].snapshot, temperature=21.0)


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
