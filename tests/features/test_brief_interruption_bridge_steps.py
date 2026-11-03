"""pytest-bdd step definitions for bridging a brief interruption within a cycle (#260).

Builds the VTherm history of a preheat modelled on the living room of 2026-11-02: a
heating state record every few minutes, the ``power`` preset and the power temperature
while the load is shed, the window action temperature while a window is open, and a few
indoor readings. Runs the real HeatingCycleService
extraction on it, then learns from the cycles with the real DeadTimeCalculationService
and GlobalLHSCalculatorService.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services.dead_time_calculation_service import (
    DeadTimeCalculationService,
)
from custom_components.intelligent_heating_pilot.domain.services.global_lhs_calculator_service import (
    GlobalLHSCalculatorService,
)
from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)

scenarios("brief_interruption_bridge.feature")

DEVICE_ID = "entry_living_room"
DAY = datetime(2026, 11, 2)
STATE_INTERVAL = timedelta(minutes=5)
EXTRACTION_MARGIN = timedelta(hours=1)
MIN_CYCLE_MINUTES = 15
MAX_CYCLE_MINUTES = 300
NORMAL_PRESET = "comfort"
LOAD_SHEDDING_PRESET = "power"
# VTherm drops the target to its power temperature while shedding the load
POWER_TEMPERATURE = 16.0
DEAD_TIME_RISE = 0.2
# Indoor readings are only listed where the profile changes: a lookup uses the last one
MID_RISE_FRACTION = 0.5
SLOPE_TOLERANCE = 0.01


def _clock(hhmm: str) -> datetime:
    """Time of the reproduction day, from 'HH:MM'."""
    hours, minutes = hhmm.split(":")
    return DAY.replace(hour=int(hours), minute=int(minutes))


@dataclass(frozen=True)
class Interruption:
    """A period during which the thermostat is not heating towards the cycle target."""

    start: datetime
    end: datetime
    target: float
    preset: str

    def covers(self, timestamp: datetime) -> bool:
        """Whether the record at this time belongs to the interruption."""
        return self.start <= timestamp < self.end


@dataclass
class Preheat:
    """The preheat described by the scenario."""

    target: float = 20.0
    start_temp: float = 19.1
    margin: float = 0.1
    start: datetime = DAY
    warming: datetime = DAY
    end: datetime = DAY
    end_temp: float = 19.9
    grace_minutes: int = 0
    interruptions: list[Interruption] = field(default_factory=list)

    def interruption_at(self, timestamp: datetime) -> Interruption | None:
        """The interruption running at this time, if any."""
        return next((i for i in self.interruptions if i.covers(timestamp)), None)


@pytest.fixture
def preheat() -> Preheat:
    """The preheat described by the scenario, and what the thermostat did meanwhile."""
    return Preheat()


@pytest.fixture
def results() -> dict[str, Any]:
    """Extracted cycles and learned values."""
    return {}


def _reading(timestamp: datetime, value: Any, **attributes: str) -> HistoricalMeasurement:
    return HistoricalMeasurement(timestamp, value, attributes, DEVICE_ID)


def _state_times(preheat: Preheat) -> list[datetime]:
    """A record every few minutes, plus the first and last record of each interruption."""
    times = set()
    timestamp = preheat.start
    while timestamp <= preheat.end:
        times.add(timestamp)
        timestamp += STATE_INTERVAL
    for interruption in preheat.interruptions:
        times.update({interruption.start, interruption.end})
    return sorted(times)


def _history(preheat: Preheat) -> HistoricalDataSet:
    """VTherm history of the preheat."""
    targets, states = [], []
    for timestamp in _state_times(preheat):
        interruption = preheat.interruption_at(timestamp)
        targets.append(_reading(timestamp, interruption.target if interruption else preheat.target))
        states.append(
            _reading(
                timestamp,
                "heat",
                hvac_action="idle" if interruption else "heating",
                hvac_mode="heat",
                preset_mode=interruption.preset if interruption else NORMAL_PRESET,
            )
        )
    warm_temp = preheat.start_temp + DEAD_TIME_RISE
    mid_rise = preheat.warming + (preheat.end - preheat.warming) * MID_RISE_FRACTION
    indoor = [
        _reading(preheat.start, preheat.start_temp),
        _reading(preheat.warming, round(warm_temp, 1)),
        _reading(mid_rise, round((warm_temp + preheat.end_temp) / 2, 1)),
        _reading(preheat.end, preheat.end_temp),
    ]
    return HistoricalDataSet(
        data={
            HistoricalDataKey.INDOOR_TEMP: indoor,
            HistoricalDataKey.TARGET_TEMP: targets,
            HistoricalDataKey.HEATING_STATE: states,
        }
    )


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        "a thermostat targeting {target:g} °C from {start:g} °C, ending a cycle {margin:g} °C "
        "below its target"
    )
)
def thermostat(preheat: Preheat, target: float, start: float, margin: float) -> None:
    """GIVEN: the setpoint, the starting temperature and the cycle-end margin."""
    preheat.target, preheat.start_temp, preheat.margin = target, start, margin


@given(
    parsers.parse(
        "a preheat starting at {start}, whose room gains 0.2 °C at {warming} and reaches "
        "{end_temp:g} °C at {end}"
    )
)
def preheat_profile(preheat: Preheat, start: str, warming: str, end_temp: float, end: str) -> None:
    """GIVEN: a slow underfloor preheat, flat until the end of its dead time."""
    preheat.start, preheat.warming, preheat.end = _clock(start), _clock(warming), _clock(end)
    preheat.end_temp = end_temp


@given(parsers.parse("a grace period of {minutes:d} minutes"))
def grace_period(preheat: Preheat, minutes: int) -> None:
    """GIVEN: the Safety Shutoff Grace Period option of the device."""
    preheat.grace_minutes = minutes


def _shed(preheat: Preheat, start: datetime, minutes: int) -> None:
    preheat.interruptions.append(
        Interruption(
            start, start + timedelta(minutes=minutes), POWER_TEMPERATURE, LOAD_SHEDDING_PRESET
        )
    )


@given(parsers.parse("the thermostat sheds its load for {minutes:d} minutes at {start}"))
def load_shedding(preheat: Preheat, minutes: int, start: str) -> None:
    """GIVEN: VTherm reports the power preset and drops the target to its power temperature."""
    _shed(preheat, _clock(start), minutes)


@given(
    parsers.parse(
        "the thermostat sheds its load for {minutes:d} minutes every {period:d} minutes "
        "from {start} to {end}"
    )
)
def repeated_load_shedding(
    preheat: Preheat, minutes: int, period: int, start: str, end: str
) -> None:
    """GIVEN: VTherm sheds the load repeatedly, heating for a minute between sheddings."""
    shedding = _clock(start)
    while shedding < _clock(end):
        _shed(preheat, shedding, minutes)
        shedding += timedelta(minutes=period)


@given(
    parsers.parse("a window drops the target to {target:g} °C for {minutes:d} minutes at {start}")
)
def window_opening(preheat: Preheat, target: float, minutes: int, start: str) -> None:
    """GIVEN: VTherm applies its window action: the target drops, the preset is kept."""
    opened = _clock(start)
    preheat.interruptions.append(
        Interruption(opened, opened + timedelta(minutes=minutes), target, NORMAL_PRESET)
    )


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("IHP extracts the heating cycles and learns from them")
def extract_and_learn(preheat: Preheat, results: dict[str, Any]) -> None:
    """WHEN: the real extraction runs, then the dead time and the global LHS are learned."""
    service = HeatingCycleService(
        temp_delta_threshold=preheat.margin,
        min_cycle_duration_minutes=MIN_CYCLE_MINUTES,
        max_cycle_duration_minutes=MAX_CYCLE_MINUTES,
        safety_shutoff_grace_minutes=preheat.grace_minutes,
    )
    cycles = asyncio.run(
        service.extract_heating_cycles(
            DEVICE_ID,
            _history(preheat),
            preheat.start - EXTRACTION_MARGIN,
            preheat.end + EXTRACTION_MARGIN,
        )
    )
    results["cycles"] = cycles
    results["dead_time"] = DeadTimeCalculationService().calculate_average_dead_time(cycles)
    results["lhs"] = GlobalLHSCalculatorService().calculate_global_lhs(cycles)


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then(parsers.parse("a single cycle is extracted, from {start} to {end}"))
def single_cycle(results: dict[str, Any], start: str, end: str) -> None:
    """THEN: the load sheddings did not fragment the preheat."""
    cycles = results["cycles"]
    assert [(c.start_time, c.end_time) for c in cycles] == [(_clock(start), _clock(end))]


@then(parsers.parse("the cycle has a dead time of {minutes:g} minutes"))
def cycle_dead_time(results: dict[str, Any], minutes: float) -> None:
    """THEN: the dead time runs from the real heating start, load sheddings included."""
    (cycle,) = results["cycles"]
    assert cycle.dead_time_cycle_minutes == pytest.approx(minutes)


@then(parsers.parse("the learned dead time is {minutes:g} minutes"))
def learned_dead_time(results: dict[str, Any], minutes: float) -> None:
    """THEN: the cycle taught its dead time."""
    assert results["dead_time"] == pytest.approx(minutes)


@then(parsers.parse("the learned heating slope is {slope:g} °C/h"))
def learned_slope(results: dict[str, Any], slope: float) -> None:
    """THEN: the cycle taught its heating slope."""
    assert results["lhs"] == pytest.approx(slope, abs=SLOPE_TOLERANCE)


@then(parsers.re(r"the first cycle ends at (?P<end>\d\d:\d\d) and is disturbed$"))
def first_cycle_disturbed(results: dict[str, Any], end: str) -> None:
    """THEN: the load shedding ended the cycle, which is excluded from learning (#255)."""
    first = results["cycles"][0]
    assert first.end_time == _clock(end)
    assert first.disturbed is True


@then(parsers.re(r"the first cycle ends at (?P<end>\d\d:\d\d)$"))
def first_cycle_ends(results: dict[str, Any], end: str) -> None:
    """THEN: the interruption ended the cycle."""
    assert results["cycles"][0].end_time == _clock(end)
