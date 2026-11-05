"""pytest-bdd step definitions for the heating slope of a cycle ending on a plateau (#267).

Builds the thermostat history of each described heating cycle from its flat and rising
stretches, runs the real HeatingCycleService extraction on it, and reads the slope of
the extracted cycles.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)

scenarios("plateau_heating_slope.feature")

DEVICE_ID = "entry_bedroom"
BASE_TIME = datetime(2026, 11, 5, 3, 0)
# A cycle ends when the room is within this margin of the target
TARGET_MARGIN = 0.2
SENSOR_STEP = 0.1
FLOAT_TOLERANCE = 1e-9
MAX_READINGS = 200


@dataclass
class Stretch:
    """A part of a cycle: flat for a duration, or rising at a rate up to a temperature."""

    minutes: float
    rate_per_hour: float = 0.0


@dataclass
class HeatingProfile:
    """Indoor temperature of a heating cycle, stretch by stretch.

    ``switched_off_at`` is the minute heating is switched off; without it the cycle ends
    when the room reaches the target margin.
    """

    start_temp: float
    stretches: list[Stretch] = field(default_factory=list)
    switched_off_at: float | None = None

    def true_temperature_at(self, minutes: float) -> float:
        """Room temperature after the given minutes of heating."""
        temp, elapsed = self.start_temp, 0.0
        for stretch in self.stretches:
            span = min(stretch.minutes, max(minutes - elapsed, 0.0))
            temp += stretch.rate_per_hour * span / 60
            elapsed += stretch.minutes
        return temp

    def reading_at(self, minutes: float) -> float:
        """Sensor reading: the room temperature down to the last 0.1 °C step."""
        steps = math.floor(self.true_temperature_at(minutes) / SENSOR_STEP + FLOAT_TOLERANCE)
        return round(steps * SENSOR_STEP, 1)


def _rise_minutes(start: float, end: float, rate: float) -> float:
    return (end - start) / rate * 60


@pytest.fixture
def plateau_context() -> dict[str, Any]:
    """Shared context: thermostat settings, described cycles and extraction results."""
    return {"profiles": [], "split_minutes": 0, "cycles": []}


def _reading(timestamp: datetime, value: Any, **attributes: str) -> HistoricalMeasurement:
    return HistoricalMeasurement(timestamp, value, attributes, DEVICE_ID)


def _record(
    history: dict[str, list[HistoricalMeasurement]],
    timestamp: datetime,
    temp: float,
    target: float,
    heating: bool,
) -> None:
    history["indoor"].append(_reading(timestamp, temp))
    history["target"].append(_reading(timestamp, target))
    history["state"].append(
        _reading(
            timestamp,
            "heat" if heating else "off",
            hvac_action="heating" if heating else "idle",
            hvac_mode="heat" if heating else "off",
        )
    )


def _history(profile: HeatingProfile, context: dict[str, Any]) -> HistoricalDataSet:
    """Thermostat history of one cycle, until the target or the switch-off is reached."""
    target = context["target_temp"]
    interval = context["reading_interval"]
    history: dict[str, list[HistoricalMeasurement]] = {"indoor": [], "target": [], "state": []}
    for index in range(MAX_READINGS):
        minutes = index * interval
        if profile.switched_off_at is not None and minutes >= profile.switched_off_at:
            break
        temp = profile.reading_at(minutes)
        _record(history, BASE_TIME + timedelta(minutes=minutes), temp, target, heating=True)
        if temp >= target - TARGET_MARGIN - FLOAT_TOLERANCE:
            break
    if profile.switched_off_at is not None:
        off_time = BASE_TIME + timedelta(minutes=profile.switched_off_at)
        temp = profile.reading_at(profile.switched_off_at)
        _record(history, off_time, temp, target, heating=False)
    return HistoricalDataSet(
        data={
            HistoricalDataKey.INDOOR_TEMP: history["indoor"],
            HistoricalDataKey.TARGET_TEMP: history["target"],
            HistoricalDataKey.HEATING_STATE: history["state"],
        }
    )


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        "a thermostat targeting {target:g} °C, read every {interval:d} minutes "
        "by a sensor reporting 0.1 °C steps"
    )
)
def thermostat(plateau_context: dict[str, Any], target: float, interval: int) -> None:
    """GIVEN: the thermostat setpoint and the sensor reporting rhythm."""
    plateau_context["target_temp"] = target
    plateau_context["reading_interval"] = interval


@given(parsers.parse("heating cycles are split every {minutes:d} minutes"))
def split_cycles(plateau_context: dict[str, Any], minutes: int) -> None:
    """GIVEN: the cycle split duration option is enabled."""
    plateau_context["split_minutes"] = minutes


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that stays flat for {flat:d} minutes, "
        "rises {rate:g} °C per hour to {plateau:g} °C, then stays flat for {hold:d} minutes "
        "until it is switched off"
    )
)
def plateau_cycle(
    plateau_context: dict[str, Any], start: float, flat: int, rate: float, plateau: float, hold: int
) -> None:
    """GIVEN: a room that rises, then settles below its target until heating stops."""
    rise = _rise_minutes(start, plateau, rate)
    plateau_context["profiles"].append(
        HeatingProfile(
            start,
            [Stretch(flat), Stretch(rise, rate), Stretch(hold)],
            switched_off_at=flat + rise + hold,
        )
    )


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that stays flat for {flat:d} minutes, "
        "rises {rate:g} °C per hour to {plateau:g} °C, stays flat for {hold:d} minutes, "
        "then rises {rate2:g} °C per hour to its target"
    )
)
def plateau_then_climb_cycle(
    plateau_context: dict[str, Any],
    start: float,
    flat: int,
    rate: float,
    plateau: float,
    hold: int,
    rate2: float,
) -> None:
    """GIVEN: a room that stalls for a while, then climbs to its target."""
    rise = _rise_minutes(start, plateau, rate)
    plateau_context["profiles"].append(
        HeatingProfile(
            start, [Stretch(flat), Stretch(rise, rate), Stretch(hold), Stretch(1e6, rate2)]
        )
    )


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that stays flat for {flat:d} minutes, "
        "then rises {rate:g} °C per hour to its target"
    )
)
def rising_cycle(plateau_context: dict[str, Any], start: float, flat: int, rate: float) -> None:
    """GIVEN: a room that warms steadily until its target."""
    plateau_context["profiles"].append(HeatingProfile(start, [Stretch(flat), Stretch(1e6, rate)]))


@given(
    parsers.parse("a heating cycle from {start:g} °C that rises {rate:g} °C per hour to its target")
)
def slow_cycle(plateau_context: dict[str, Any], start: float, rate: float) -> None:
    """GIVEN: a slow heating system, such as underfloor heating, warming until its target."""
    plateau_context["profiles"].append(HeatingProfile(start, [Stretch(1e6, rate)]))


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("IHP extracts the heating cycles")
def extract_cycles(plateau_context: dict[str, Any]) -> None:
    """WHEN: the real extraction runs on the history of every described cycle."""
    service = HeatingCycleService(
        temp_delta_threshold=TARGET_MARGIN,
        cycle_split_duration_minutes=plateau_context["split_minutes"],
    )
    for profile in plateau_context["profiles"]:
        history = _history(profile, plateau_context)
        plateau_context["cycles"].extend(
            asyncio.run(
                service.extract_heating_cycles(
                    DEVICE_ID, history, BASE_TIME, BASE_TIME + timedelta(hours=12)
                )
            )
        )


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


def _single_cycle(plateau_context: dict[str, Any]) -> Any:
    cycles = plateau_context["cycles"]
    assert len(cycles) == 1, f"Expected one extracted cycle, got {len(cycles)}"
    return cycles[0]


@then(parsers.parse("the cycle has a heating slope of {slope:g} °C/h"))
def cycle_slope(plateau_context: dict[str, Any], slope: float) -> None:
    """THEN: the slope describes the rise of the room."""
    assert _single_cycle(plateau_context).avg_heating_slope == pytest.approx(slope)


@then(parsers.parse("the cycle has a dead time of {minutes:g} minutes"))
def cycle_dead_time(plateau_context: dict[str, Any], minutes: float) -> None:
    """THEN: the dead time is not affected by the plateau."""
    assert _single_cycle(plateau_context).dead_time_cycle_minutes == pytest.approx(minutes)


@then(parsers.parse("the cycle lasts {minutes:d} minutes and ends at {temp:g} °C"))
def cycle_bounds(plateau_context: dict[str, Any], minutes: int, temp: float) -> None:
    """THEN: the cycle still ends when heating stopped, with the temperature it ended at."""
    cycle = _single_cycle(plateau_context)
    assert cycle.start_time == BASE_TIME
    assert cycle.end_time == BASE_TIME + timedelta(minutes=minutes)
    assert cycle.end_temp == pytest.approx(temp)


@then(parsers.parse("every sub-cycle has a heating slope of {slope:g} °C/h"))
def sub_cycle_slopes(plateau_context: dict[str, Any], slope: float) -> None:
    """THEN: no sub-cycle covers the plateau."""
    cycles = plateau_context["cycles"]
    assert len(cycles) > 1, "The cycle should have been split"
    assert [c.avg_heating_slope for c in cycles] == pytest.approx([slope] * len(cycles))


@then(parsers.parse("the last sub-cycle ends {minutes:d} minutes after the cycle start"))
def last_sub_cycle_end(plateau_context: dict[str, Any], minutes: int) -> None:
    """THEN: the sub-cycles stop where the heating phase ends."""
    assert plateau_context["cycles"][-1].end_time == BASE_TIME + timedelta(minutes=minutes)
