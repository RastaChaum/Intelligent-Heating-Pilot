"""pytest-bdd step definitions for the dead time and heating slope of a cycle (#245).

Builds the thermostat history of each described heating cycle, runs the real
HeatingCycleService extraction on it, and learns the dead time with the real
DeadTimeCalculationService.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services.dead_time_calculation_service import (
    DeadTimeCalculationService,
)
from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)

scenarios("cycle_dead_time_and_slope.feature")

DEVICE_ID = "entry_living_room"
BASE_TIME = datetime(2026, 1, 12, 5, 0)
# Each described cycle runs in its own morning, far from the others
CYCLE_SPACING = timedelta(days=1)
# A cycle ends when the room is within this margin of the target
TARGET_MARGIN = 0.2
SENSOR_DECIMALS = 1
MAX_READINGS = 100
FLOAT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class HeatingProfile:
    """Indoor temperature of a heating cycle: a settling phase, then a steady rise."""

    start_temp: float
    drop: float
    settle_minutes: int
    rise_per_hour: float
    switched_off_at: float | None = None

    def temperature_at(self, minutes: int) -> float:
        """Sensor reading after the given minutes of heating."""
        if minutes <= self.settle_minutes:
            temp = self.start_temp - self.drop * minutes / self.settle_minutes
        else:
            rising_minutes = minutes - self.settle_minutes
            temp = self.start_temp - self.drop + self.rise_per_hour * rising_minutes / 60
        return round(temp, SENSOR_DECIMALS)


@pytest.fixture
def cycle_context() -> dict[str, Any]:
    """Shared context: thermostat settings, described cycles and extraction results."""
    return {"profiles": [], "split_minutes": 0, "cycles": []}


def _reading(timestamp: datetime, value: Any, **attributes: str) -> HistoricalMeasurement:
    return HistoricalMeasurement(timestamp, value, attributes, DEVICE_ID)


def _history(
    profile: HeatingProfile, start: datetime, context: dict[str, Any]
) -> HistoricalDataSet:
    """Thermostat history of one cycle, until the target or the switch-off is reached."""
    target = context["target_temp"]
    interval = context["reading_interval"]
    indoor, targets, states = [], [], []
    for index in range(MAX_READINGS):
        minutes = index * interval
        timestamp = start + timedelta(minutes=minutes)
        temp = profile.temperature_at(minutes)
        switched_off = (
            profile.switched_off_at is not None
            and temp >= profile.switched_off_at - FLOAT_TOLERANCE
        )
        indoor.append(_reading(timestamp, temp))
        targets.append(_reading(timestamp, target))
        states.append(
            _reading(
                timestamp,
                "off" if switched_off else "heat",
                hvac_action="idle" if switched_off else "heating",
                hvac_mode="off" if switched_off else "heat",
            )
        )
        if switched_off or temp >= target - TARGET_MARGIN - FLOAT_TOLERANCE:
            break
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
        "a thermostat targeting {target:g} °C, with an indoor reading every {interval:d} "
        "minutes rounded to 0.1 °C"
    )
)
def thermostat(cycle_context: dict[str, Any], target: float, interval: int) -> None:
    """GIVEN: the thermostat setpoint and the sensor reporting rhythm."""
    cycle_context["target_temp"] = target
    cycle_context["reading_interval"] = interval


@given(parsers.parse("heating cycles are split every {minutes:d} minutes"))
def split_cycles(cycle_context: dict[str, Any], minutes: int) -> None:
    """GIVEN: the cycle split duration option is enabled."""
    cycle_context["split_minutes"] = minutes


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that stays flat for {minutes:d} minutes, "
        "then rises {rate:g} °C per hour"
    )
)
def flat_then_rising_cycle(
    cycle_context: dict[str, Any], start: float, minutes: int, rate: float
) -> None:
    """GIVEN: a room that takes a while to react, then heats steadily."""
    cycle_context["profiles"].append(HeatingProfile(start, 0.0, minutes, rate))


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that falls {drop:g} °C in {minutes:d} minutes, "
        "then rises {rate:g} °C per hour"
    )
)
def falling_then_rising_cycle(
    cycle_context: dict[str, Any], start: float, drop: float, minutes: int, rate: float
) -> None:
    """GIVEN: a room that keeps cooling after heating starts, then heats steadily."""
    cycle_context["profiles"].append(HeatingProfile(start, drop, minutes, rate))


@given(
    parsers.parse(
        "a heating cycle from {start:g} °C that falls {drop:g} °C in {minutes:d} minutes, "
        "then rises {rate:g} °C per hour until it is switched off at {stop:g} °C"
    )
)
def switched_off_cycle(
    cycle_context: dict[str, Any],
    start: float,
    drop: float,
    minutes: int,
    rate: float,
    stop: float,
) -> None:
    """GIVEN: heating switched off just as the room climbs back above its start."""
    cycle_context["profiles"].append(HeatingProfile(start, drop, minutes, rate, stop))


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("IHP extracts the heating cycles")
def extract_cycles(cycle_context: dict[str, Any]) -> None:
    """WHEN: the real extraction runs on the history of every described cycle."""
    service = HeatingCycleService(
        temp_delta_threshold=TARGET_MARGIN,
        cycle_split_duration_minutes=cycle_context["split_minutes"],
    )
    for index, profile in enumerate(cycle_context["profiles"]):
        start = BASE_TIME + index * CYCLE_SPACING
        history = _history(profile, start, cycle_context)
        cycle_context["cycles"].extend(
            asyncio.run(
                service.extract_heating_cycles(DEVICE_ID, history, start, start + CYCLE_SPACING / 2)
            )
        )


@when("IHP learns the dead time from them")
def learn_dead_time(cycle_context: dict[str, Any]) -> None:
    """WHEN: the dead time is averaged over the extracted cycles."""
    cycle_context["learned_dead_time"] = DeadTimeCalculationService().calculate_average_dead_time(
        cycle_context["cycles"]
    )


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


def _single_cycle(cycle_context: dict[str, Any]) -> Any:
    cycles = cycle_context["cycles"]
    assert len(cycles) == 1, f"Expected one extracted cycle, got {len(cycles)}"
    return cycles[0]


@then(parsers.parse("the cycle has a dead time of {minutes:g} minutes"))
def cycle_dead_time(cycle_context: dict[str, Any], minutes: float) -> None:
    """THEN: the dead time ends at the first reading 0.2 °C above the start."""
    assert _single_cycle(cycle_context).dead_time_cycle_minutes == pytest.approx(minutes)


@then(parsers.parse("the cycle has a heating slope of {slope:g} °C/h"))
def cycle_slope(cycle_context: dict[str, Any], slope: float) -> None:
    """THEN: the slope is the rise rate after the dead time."""
    assert _single_cycle(cycle_context).avg_heating_slope == pytest.approx(slope)


@then(parsers.parse("the learned dead time is {minutes:g} minutes"))
def learned_dead_time(cycle_context: dict[str, Any], minutes: float) -> None:
    """THEN: only the cycles kept for the heating slope were averaged."""
    assert cycle_context["learned_dead_time"] == pytest.approx(minutes)


@then(parsers.parse("every sub-cycle has a heating slope of {slope:g} °C/h"))
def sub_cycle_slopes(cycle_context: dict[str, Any], slope: float) -> None:
    """THEN: no sub-cycle is inflated or emptied by the dead time."""
    cycles = cycle_context["cycles"]
    assert len(cycles) > 1, "The cycle should have been split"
    assert [c.avg_heating_slope for c in cycles] == pytest.approx([slope] * len(cycles))


@then(
    parsers.parse(
        "only the first sub-cycle has a dead time, of {minutes:g} minutes, "
        "and it starts with the cycle"
    )
)
def first_sub_cycle_dead_time(cycle_context: dict[str, Any], minutes: float) -> None:
    """THEN: the dead time is kept once, measured from the cycle start."""
    first, *others = cycle_context["cycles"]
    assert first.start_time == BASE_TIME
    assert first.dead_time_cycle_minutes == pytest.approx(minutes)
    assert all(c.dead_time_cycle_minutes is None for c in others)
