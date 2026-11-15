"""pytest-bdd steps for wake-up sources: the whole stack over a simulated thermostat."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    SlotAction,
    WakeUpSourceConfig,
)
from tests.native_stack import block
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot
from tests.wake_up_stack import MONDAY_NOON, WakeUpStack

scenarios("wake_up_source.feature")


@pytest.fixture
def context() -> dict:
    return {"sources": [], "blocks": [], "values": {}, "with_schedule": False}


def _tomorrow_at(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    day = MONDAY_NOON + timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


@given(parsers.parse('the thermostat is in the "{preset}" preset at {temp:f}°C'))
def thermostat_state(context: dict, preset: str, temp: float) -> None:
    context["climate"] = FakeClimate(make_snapshot(preset=preset, temperature=temp))


@given(parsers.parse('it offers the presets "{a}", "{b}" and "{c}"'))
def thermostat_presets(context: dict, a: str, b: str, c: str) -> None:
    assert context["climate"].snapshot.available_presets == (a, b, c)


@given(parsers.parse('a wake-up source "{entity}" with the target preset "{preset}"'))
def source_with_preset(context: dict, entity: str, preset: str) -> None:
    context["sources"].append(WakeUpSourceConfig(entity, SlotAction(preset=preset)))
    context["source"] = entity


@given(
    parsers.parse(
        'a wake-up source "{entity}" with the target preset "{preset}" and a hold of {minutes:d} minutes'
    )
)
def source_with_hold(context: dict, entity: str, preset: str, minutes: int) -> None:
    context["sources"].append(
        WakeUpSourceConfig(entity, SlotAction(preset=preset), hold=timedelta(minutes=minutes))
    )
    context["source"] = entity


@given(parsers.parse('a wake-up source "{entity}" taking its target from the schedule'))
def source_from_schedule(context: dict, entity: str) -> None:
    context["sources"].append(WakeUpSourceConfig(entity, target_from_schedule=True))
    context["source"] = entity
    context["with_schedule"] = True


@given(
    parsers.parse(
        'a wake-up source "{entity}" taking its target from the schedule with the fallback preset "{preset}"'
    )
)
def source_from_schedule_with_fallback(context: dict, entity: str, preset: str) -> None:
    context["sources"].append(
        WakeUpSourceConfig(entity, SlotAction(preset=preset), target_from_schedule=True)
    )
    context["source"] = entity
    context["with_schedule"] = True


@given(
    parsers.parse('the schedule has a block from {start} to {end} with the data preset "{preset}"')
)
def schedule_block_between(context: dict, start: str, end: str, preset: str) -> None:
    context["with_schedule"] = True
    context["blocks"].append(block(start, end, {"preset": preset}))


@given("the schedule has no block")
def schedule_without_block(context: dict) -> None:
    context["with_schedule"] = True
    context["blocks"] = []


@given(parsers.parse('the schedule has a block at {start} with the data preset "{preset}"'))
def schedule_block(context: dict, start: str, preset: str) -> None:
    context["with_schedule"] = True
    context["blocks"].append(block(start, "22:00", {"preset": preset}))


@given(parsers.parse("the source is set to {hhmm} tomorrow"))
def source_tomorrow(context: dict, hhmm: str) -> None:
    context["values"][context["source"]] = _tomorrow_at(hhmm)


@given(parsers.parse("the source is set to {minutes:d} minutes ago"))
def source_in_the_past(context: dict, minutes: int) -> None:
    context["values"][context["source"]] = MONDAY_NOON - timedelta(minutes=minutes)


@when("the anticipated start is reached")
def anticipated_start_reached(context: dict) -> None:
    stack = WakeUpStack(
        context["climate"], context["sources"], with_schedule=context["with_schedule"]
    )
    stack.blocks = context["blocks"]
    for entity, value in context["values"].items():
        stack.set_source(entity, value)
    stack.restart()
    context["stack"] = stack
    context["result"] = stack.recalculate()


@then(parsers.parse("the next deadline is at {hhmm} tomorrow"))
def next_deadline(context: dict, hhmm: str) -> None:
    assert context["result"]["next_schedule_time"] == _tomorrow_at(hhmm)


@then(parsers.parse('the thermostat preset becomes "{preset}"'))
def preset_becomes(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset
    assert context["stack"].commands("set_preset_mode")


@when("the wake-up time has passed")
def wake_up_time_passed(context: dict) -> None:
    stack = context["stack"]
    deadline = context["values"][context["source"]]
    stack.advance(deadline - stack.now + timedelta(seconds=5))
    stack.set_source(context["source"], None)  # the phone shows no alarm any more
    stack.recalculate()


@when("the hold ends")
def hold_ends(context: dict) -> None:
    stack = context["stack"]
    source = next(s for s in context["sources"] if s.entity_id == context["source"])
    deadline = context["values"][context["source"]]
    hold_end = deadline + (source.hold or timedelta(0))
    # A scheduler slot that comes before bounds the hold: the timer is at that slot
    ends = [when for when, _callback in stack.timers if when > stack.now]
    stack.advance(max([hold_end, *ends[:0]]) - stack.now if not ends else min(ends) - stack.now)
    stack.fire_due_timers()


@when(parsers.parse('somebody sets the thermostat to the "{preset}" preset'))
def somebody_sets_the_thermostat(context: dict, preset: str) -> None:
    context["climate"].snapshot = make_snapshot(preset=preset, temperature=23.0)


@then(parsers.parse('the thermostat preset is still "{preset}"'))
def preset_still(context: dict, preset: str) -> None:
    assert context["climate"].snapshot.preset == preset


@then("the thermostat was never restored")
def never_restored(context: dict) -> None:
    stack = context["stack"]
    restored = [
        data
        for data in stack.commands("set_preset_mode")
        if data and data.get("preset_mode") == "eco"
    ]
    assert restored == []


@then("there is no next deadline")
def no_deadline(context: dict) -> None:
    assert context["result"]["next_schedule_time"] is None


@then("no command is sent to the thermostat")
def no_command(context: dict) -> None:
    assert context["stack"].service_calls == []
