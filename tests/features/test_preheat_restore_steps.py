"""pytest-bdd steps for undoing a preheat safely (record, restore, restart).

The whole stack runs for real over a simulated thermostat and an in-memory record: see
``tests/native_stack.py``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.native_stack import MONDAY_NOON, NativeStack, block
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot

scenarios("preheat_restore.feature")

SLOT_START = MONDAY_NOON.replace(hour=18, minute=0)


@pytest.fixture
def context() -> dict:
    return {"blocks": [], "commands_at_start": 0}


@given("direct control of native schedules is on")
def drive_on(context: dict) -> None:
    context["drive"] = True


@given(parsers.parse('the next block starts at {start} with the data preset "{preset}"'))
def next_block(context: dict, start: str, preset: str) -> None:
    context["blocks"].append(block(start, "22:00", {"preset": preset}))


@given(parsers.parse('the thermostat is in the "{preset}" preset at {temp:f}°C'))
def thermostat_in_preset(context: dict, preset: str, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset=preset, temperature=temp))


@given(parsers.parse("the thermostat is set by hand to {temp:f}°C without a preset"))
def thermostat_by_hand(context: dict, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset="none", temperature=temp))


@given("a preheat is in progress for that block")
def preheat_in_progress(context: dict) -> None:
    stack = NativeStack(context["climate"], drive=context["drive"])
    stack.blocks = context["blocks"]
    stack.recalculate()
    assert stack.control.is_preheating_active(), "the preheat should have started"
    context["stack"] = stack
    context["commands_at_start"] = len(stack.service_calls)


@given(parsers.parse('the user selects the "{preset}" preset by hand'))
def user_selects_preset(context: dict, preset: str) -> None:
    context["climate"].snapshot = replace(context["climate"].snapshot, preset=preset)


@given("it is 3 minutes before the block starts")
def three_minutes_before(context: dict) -> None:
    context["stack"].now = SLOT_START - timedelta(minutes=3)


@when("the block is removed from the schedule")
def block_removed(context: dict) -> None:
    context["stack"].blocks.clear()


@when("Home Assistant restarts")
def home_assistant_restarts(context: dict) -> None:
    context["stack"].restart()


@when("the start time of the block is reached")
def start_time_reached(context: dict) -> None:
    context["stack"].now = SLOT_START


@when("IHP recalculates")
def ihp_recalculates(context: dict) -> None:
    context["stack"].recalculate()


@then(parsers.parse('the thermostat preset is back to "{preset}"'))
@then(parsers.parse('the thermostat preset is still "{preset}"'))
def preset_is(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset


@then(parsers.parse("the thermostat target is back to {temp:f}°C"))
def target_is_back(context: dict, temp: float) -> None:
    assert context["climate"].snapshot.temperature == temp
    assert context["climate"].snapshot.preset == "none"


@then("IHP wrote nothing to the thermostat after the preheat started")
def nothing_written_after_start(context: dict) -> None:
    assert len(context["stack"].service_calls) == context["commands_at_start"]


@then("IHP sends no new command")
def no_new_command(context: dict) -> None:
    assert len(context["stack"].service_calls) == context["commands_at_start"]


@then("the preheat is still in progress")
def preheat_still_in_progress(context: dict) -> None:
    assert context["stack"].control.is_preheating_active() is True
    assert context["stack"].store.record is not None


@then("nothing is left recorded")
def nothing_recorded(context: dict) -> None:
    assert context["stack"].store.record is None
