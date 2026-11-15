"""Wake-up sources through the whole stack: bad values, a thermostat that cannot take the target."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    SlotAction,
    WakeUpSourceConfig,
)
from tests.unit.application.actuators.fakes import FakeClimate, make_snapshot
from tests.wake_up_stack import MONDAY_NOON, WakeUpStack

ALARM = "sensor.phone_next_alarm"
OTHER = "sensor.partner_next_alarm"


def _stack(
    climate: FakeClimate | None = None,
    sources: list[WakeUpSourceConfig] | None = None,
    **kwargs,
) -> WakeUpStack:
    sources = sources or [WakeUpSourceConfig(ALARM, SlotAction(preset="comfort"))]
    return WakeUpStack(climate or FakeClimate(), sources, with_schedule=False, **kwargs)


@pytest.mark.parametrize(
    "value",
    [
        None,
        MONDAY_NOON - timedelta(minutes=1),
        MONDAY_NOON,
        MONDAY_NOON + timedelta(hours=25),
        MONDAY_NOON + timedelta(days=30),
    ],
    ids=["unknown", "past", "now", "beyond-horizon", "far-away"],
)
def test_an_unusable_value_sends_nothing(value) -> None:
    stack = _stack()
    stack.set_source(ALARM, value)

    result = stack.recalculate()

    assert result["next_schedule_time"] is None
    assert stack.service_calls == []


def test_a_thermostat_that_is_off_is_left_alone() -> None:
    climate = FakeClimate(make_snapshot(hvac_mode="off"))
    stack = _stack(climate)
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    stack.recalculate()

    assert stack.service_calls == []
    assert climate.snapshot.hvac_mode == "off"


def test_a_preset_the_thermostat_does_not_offer_is_not_applied() -> None:
    stack = _stack(sources=[WakeUpSourceConfig(ALARM, SlotAction(preset="party"))])
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    stack.recalculate()

    assert stack.commands("set_preset_mode") == []
    assert stack.climate.snapshot.preset == "eco"


def test_a_temperature_target_is_applied_as_a_temperature_not_a_preset() -> None:
    stack = _stack(sources=[WakeUpSourceConfig(ALARM, SlotAction(temperature=21.5))])
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    stack.recalculate()

    assert stack.commands("set_preset_mode") == []
    assert stack.commands("set_temperature") == [
        {"entity_id": "climate.living_room", "temperature": 21.5}
    ]


def test_the_wake_up_source_never_changes_the_heating_mode() -> None:
    stack = _stack()
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    stack.recalculate()

    assert stack.commands("set_hvac_mode") == []
    assert stack.climate.snapshot.hvac_mode == "heat"


def test_two_devices_sharing_one_alarm_keep_their_own_target_and_record() -> None:
    living, bedroom = FakeClimate(), FakeClimate()
    living_stack = _stack(living, [WakeUpSourceConfig(ALARM, SlotAction(preset="comfort"))])
    bedroom_stack = _stack(bedroom, [WakeUpSourceConfig(ALARM, SlotAction(preset="boost"))])
    for stack in (living_stack, bedroom_stack):
        stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    living_stack.recalculate()
    bedroom_stack.recalculate()

    assert living.snapshot.preset == "comfort"
    assert bedroom.snapshot.preset == "boost"
    assert living_stack.store is not bedroom_stack.store


def test_the_earliest_of_two_alarms_drives_the_thermostat() -> None:
    sources = [
        WakeUpSourceConfig(ALARM, SlotAction(preset="comfort")),
        WakeUpSourceConfig(OTHER, SlotAction(preset="boost")),
    ]
    stack = _stack(sources=sources)
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=10))
    stack.set_source(OTHER, MONDAY_NOON + timedelta(hours=7))

    result = stack.recalculate()

    assert result["scheduler_entity"] == OTHER
    assert stack.climate.snapshot.preset == "boost"


def test_ihp_disabled_sends_nothing() -> None:
    stack = _stack()
    stack.set_source(ALARM, MONDAY_NOON + timedelta(hours=8))

    with patch("homeassistant.util.dt.now", return_value=stack.now):
        asyncio.run(stack.orchestrator.calculate_and_schedule_anticipation(False))

    assert stack.service_calls == []
