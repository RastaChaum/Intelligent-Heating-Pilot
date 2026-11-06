"""pytest-bdd step definitions for late preheat slot hour scenarios (#254).

Runs the real cycle extraction on a synthetic history, then files the extracted
cycles with the real contextual LHS calculator, so the slot found during
extraction must reach the hour the slot reads.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services.contextual_hour import (
    contextual_hour,
)
from custom_components.intelligent_heating_pilot.domain.services.contextual_lhs_calculator_service import (
    ContextualLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)

scenarios("late_preheat_slot_hour.feature")

DAY = datetime(2026, 11, 1, tzinfo=UTC)
START_TEMP = 18.9
# Highest temperature recorded before the end: below the target minus the detection threshold
LAST_TEMP_BEFORE_END = 19.6
READING_INTERVAL = timedelta(minutes=10)
VTHERM = "climate.living_room"
NEXT_SCHEDULE_SENSOR = "sensor.living_room_next_schedule_time"


def _at(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return DAY.replace(hour=hour, minute=minute)


@pytest.fixture
def preheat_context() -> dict:
    """Shared state between steps."""
    return {"data": {}, "split_minutes": 0}


def _record(context: dict, key: HistoricalDataKey, measurement: HistoricalMeasurement) -> None:
    context["data"].setdefault(key, []).append(measurement)


@given(parsers.parse("the room heats toward {target:f} degrees"))
def room_target(preheat_context: dict, target: float) -> None:
    """GIVEN: The thermostat target during the whole day."""
    preheat_context["target"] = target
    _record(
        preheat_context,
        HistoricalDataKey.TARGET_TEMP,
        HistoricalMeasurement(DAY, target, {}, VTHERM),
    )


@given(parsers.parse("cycles are split every {minutes:d} minutes"))
def split_cycles(preheat_context: dict, minutes: int) -> None:
    """GIVEN: Cycle splitting is enabled."""
    preheat_context["split_minutes"] = minutes


@given(parsers.parse("a {target:f} degree slot came due at {slot}"))
def slot_came_due(preheat_context: dict, target: float, slot: str) -> None:
    """GIVEN: IHP's Next Schedule Time sensor recorded this slot."""
    _record(
        preheat_context,
        HistoricalDataKey.SCHEDULED_SLOT,
        HistoricalMeasurement(_at(slot), target, {}, NEXT_SCHEDULE_SENSOR),
    )


@given(parsers.parse("the room heated from {start} until it reached the target at {end}"))
def room_heated(preheat_context: dict, start: str, end: str) -> None:
    """GIVEN: The VTherm heated steadily from start, and reached the target at end."""
    start_time, end_time = _at(start), _at(end)
    ticks = []
    tick = start_time
    while tick < end_time:
        ticks.append(tick)
        tick += READING_INTERVAL
    rise_per_tick = (LAST_TEMP_BEFORE_END - START_TEMP) / max(len(ticks) - 1, 1)
    readings = [(tick, START_TEMP + rise_per_tick * index) for index, tick in enumerate(ticks)]
    readings.append((end_time, preheat_context["target"]))
    for timestamp, temperature in readings:
        _record(
            preheat_context,
            HistoricalDataKey.INDOOR_TEMP,
            HistoricalMeasurement(timestamp, temperature, {}, VTHERM),
        )
        _record(
            preheat_context,
            HistoricalDataKey.HEATING_STATE,
            HistoricalMeasurement(
                timestamp, "heat", {"hvac_action": "heating", "hvac_mode": "heat"}, VTHERM
            ),
        )


@when("the heating cycles are extracted and contextual slopes are learned")
def extract_and_learn(preheat_context: dict) -> None:
    """WHEN: The real extraction runs, then the cycles are grouped by contextual hour."""
    service = HeatingCycleService(
        temp_delta_threshold=0.2,
        cycle_split_duration_minutes=preheat_context["split_minutes"],
    )
    cycles = asyncio.run(
        service.extract_heating_cycles(
            device_id=VTHERM,
            history_data_set=HistoricalDataSet(data=preheat_context["data"]),
            start_time=DAY,
            end_time=DAY + timedelta(days=1),
        )
    )
    calculator = ContextualLHSCalculatorService(local_tz=UTC)
    preheat_context["cycles"] = cycles
    preheat_context["by_hour"] = calculator.group_cycles_by_hour(cycles)
    preheat_context["learned"] = calculator.calculate_contextual_lhs_by_hour(cycles).learned


def _cycles_read_by_slot(context: dict, slot: str) -> list[HeatingCycle]:
    return context["by_hour"][contextual_hour(_at(slot))]


@then(parsers.parse("the cycle is learned for a slot at {slot}"))
def cycle_learned_for_slot(preheat_context: dict, slot: str) -> None:
    """THEN: The single cycle is filed under the slot's hour, and its slope learned there."""
    cycles = preheat_context["cycles"]
    assert len(cycles) == 1
    assert _cycles_read_by_slot(preheat_context, slot) == cycles
    hour = contextual_hour(_at(slot))
    assert preheat_context["learned"][hour] == pytest.approx(cycles[0].avg_heating_slope)


@then(parsers.parse("the cycle is not learned for a slot at {slot}"))
def cycle_not_learned_for_slot(preheat_context: dict, slot: str) -> None:
    """THEN: The slot's hour holds no cycle."""
    assert _cycles_read_by_slot(preheat_context, slot) == []
    assert contextual_hour(_at(slot)) not in preheat_context["learned"]


@then("there are several cycles")
def several_cycles(preheat_context: dict) -> None:
    """THEN: The preheat was split."""
    assert len(preheat_context["cycles"]) > 1


@then(parsers.parse("every cycle is learned for a slot at {slot}"))
def every_cycle_learned_for_slot(preheat_context: dict, slot: str) -> None:
    """THEN: All sub-cycles are filed under the slot's hour."""
    assert _cycles_read_by_slot(preheat_context, slot) == preheat_context["cycles"]
