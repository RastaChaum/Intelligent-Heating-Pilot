"""pytest-bdd steps for native schedule preheating (direct control of the climate).

The whole stack runs for real over a simulated thermostat: see ``tests/native_stack.py``.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.native_stack import NativeStack, block
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot

scenarios("native_schedule_preheat.feature")


@pytest.fixture
def context() -> dict:
    return {"drive": False, "blocks": [], "state": "off"}


@given(parsers.parse('the thermostat is in the "{preset}" preset at {temp:f}°C'))
def thermostat_state(context: dict, preset: str, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset=preset, temperature=temp))


@given(parsers.parse('it offers the presets "{a}", "{b}" and "{c}"'))
def thermostat_presets(context: dict, a: str, b: str, c: str) -> None:
    assert context["climate"].snapshot.available_presets == (a, b, c)


@given("direct control of native schedules is on")
def drive_on(context: dict) -> None:
    context["drive"] = True


@given(parsers.parse('the next block starts at {start} with the data preset "{preset}"'))
def next_block_preset(context: dict, start: str, preset: str) -> None:
    context["blocks"].append(block(start, "22:00", {"preset": preset}))


@given(parsers.parse("the next block starts at {start} with the data temperature {temp:f}"))
def next_block_temperature(context: dict, start: str, temp: float) -> None:
    context["blocks"].append(block(start, "22:00", {"temperature": temp}))


@given(parsers.parse("the next block starts at {start} with no data"))
def next_block_without_data(context: dict, start: str) -> None:
    context["blocks"].append(block(start, "22:00"))


@given(
    parsers.parse(
        'the next block starts at {start} with the data preset "{preset}" and temperature {temp:f}'
    )
)
def next_block_both(context: dict, start: str, preset: str, temp: float) -> None:
    context["blocks"].append(block(start, "22:00", {"preset": preset, "temperature": temp}))


@given(parsers.parse('the schedule is running a block until {end} with the data preset "{preset}"'))
def running_block(context: dict, end: str, preset: str) -> None:
    context["state"] = "on"
    context["blocks"].insert(0, block("10:00", end, {"preset": preset}))


@when("the anticipated start is reached")
def anticipated_start_reached(context: dict) -> None:
    stack = NativeStack(context["climate"], drive=context["drive"])
    stack.blocks = context["blocks"]
    stack.schedule_state = context["state"]
    stack.restart()
    stack.recalculate()
    context["stack"] = stack


@then(parsers.parse('the thermostat preset becomes "{preset}"'))
def preset_becomes(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset
    assert context["stack"].commands("set_preset_mode")


@then(parsers.parse("the thermostat target becomes {temp:f}°C"))
def target_becomes(context: dict, temp: float) -> None:
    assert context["climate"].snapshot.temperature == temp


@then("no preset was set")
def no_preset_set(context: dict) -> None:
    assert context["stack"].commands("set_preset_mode") == []


@then("no temperature was set")
def no_temperature_set(context: dict) -> None:
    assert context["stack"].commands("set_temperature") == []


@then("no command is sent to the thermostat")
def no_command(context: dict) -> None:
    assert context["stack"].service_calls == []


@then(parsers.parse('the thermostat preset is still "{preset}"'))
def preset_still(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset
