"""pytest-bdd step definitions for learning slow cycles and ignoring disturbed ones (#255).

Builds the VTherm history of each described heating cycle, including the presets
VTherm records in safety mode (``safety``) and during load shedding (``power``),
runs the real HeatingCycleService extraction on it, and learns from the cycles with
the real DeadTimeCalculationService and GlobalLHSCalculatorService.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.constants import DEFAULT_LEARNED_SLOPE
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

scenarios("slow_and_disturbed_cycle_learning.feature")

DEVICE_ID = "entry_living_room"
BASE_TIME = datetime(2026, 1, 12, 5, 0)
EXTRACTION_WINDOW = timedelta(hours=12)
# A cycle ends when the room is within this margin of the target
TARGET_MARGIN = 0.2
SENSOR_DECIMALS = 1
MAX_READINGS = 100
FLOAT_TOLERANCE = 1e-9
NORMAL_PRESET = "comfort"
SAFETY_PRESET = "safety"
LOAD_SHEDDING_PRESET = "power"
# VTherm drops the target to its power temperature while shedding the load
POWER_TEMPERATURE = 16.0


@dataclass
class HeatingProfile:
    """Indoor temperature of a heating cycle and what the thermostat reported meanwhile."""

    start_temp: float
    flat_minutes: int
    rise_per_hour: float
    safety_from: int | None = None
    safety_to: int | None = None
    load_shedding_at: int | None = None
    readings: list[int] = field(default_factory=list)

    def temperature_at(self, minutes: int) -> float:
        """Sensor reading after the given minutes of heating."""
        rising_minutes = max(0, minutes - self.flat_minutes)
        return round(self.start_temp + self.rise_per_hour * rising_minutes / 60, SENSOR_DECIMALS)

    def preset_at(self, minutes: int) -> str:
        """Preset VTherm reports at the given minute."""
        if self.load_shedding_at is not None and minutes >= self.load_shedding_at:
            return LOAD_SHEDDING_PRESET
        in_safety = (
            self.safety_from is not None
            and self.safety_to is not None
            and self.safety_from <= minutes <= self.safety_to
        )
        if in_safety:
            return SAFETY_PRESET
        return NORMAL_PRESET


@pytest.fixture
def cycle_context() -> dict[str, Any]:
    """Shared context: thermostat settings, the described cycle and the learning results."""
    return {"profile": None, "cycles": []}


def _reading(timestamp: datetime, value: Any, **attributes: str) -> HistoricalMeasurement:
    return HistoricalMeasurement(timestamp, value, attributes, DEVICE_ID)


def _history(profile: HeatingProfile, context: dict[str, Any]) -> HistoricalDataSet:
    """VTherm history of the cycle, until the target or the load shedding is reached."""
    target = context["target_temp"]
    interval = context["reading_interval"]
    indoor, targets, states = [], [], []
    for index in range(MAX_READINGS):
        minutes = index * interval
        timestamp = BASE_TIME + timedelta(minutes=minutes)
        temp = profile.temperature_at(minutes)
        preset = profile.preset_at(minutes)
        shed = preset == LOAD_SHEDDING_PRESET
        indoor.append(_reading(timestamp, temp))
        targets.append(_reading(timestamp, POWER_TEMPERATURE if shed else target))
        states.append(
            _reading(
                timestamp,
                "heat",
                hvac_action="idle" if shed else "heating",
                hvac_mode="heat",
                preset_mode=preset,
            )
        )
        if shed or temp >= target - TARGET_MARGIN - FLOAT_TOLERANCE:
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
    cycle_context["profile"] = HeatingProfile(start, minutes, rate)


@given(parsers.parse("a heating cycle from {start:g} °C that rises {rate:g} °C per hour"))
def rising_cycle(cycle_context: dict[str, Any], start: float, rate: float) -> None:
    """GIVEN: a room close to its target that heats from the first minute."""
    cycle_context["profile"] = HeatingProfile(start, 0, rate)


@given(
    parsers.parse(
        "the thermostat is in safety mode from minute {start:d} to minute {end:d}",
    )
)
def safety_mode(cycle_context: dict[str, Any], start: int, end: int) -> None:
    """GIVEN: VTherm reports the safety preset for a while, keeping the target."""
    cycle_context["profile"].safety_from = start
    cycle_context["profile"].safety_to = end


@given(parsers.parse("the thermostat sheds its load at minute {minute:d}"))
def load_shedding(cycle_context: dict[str, Any], minute: int) -> None:
    """GIVEN: VTherm reports the power preset and drops the target to its power temperature."""
    cycle_context["profile"].load_shedding_at = minute


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("IHP extracts the heating cycles and learns from them")
def extract_and_learn(cycle_context: dict[str, Any]) -> None:
    """WHEN: the real extraction runs, then the dead time and the global LHS are learned."""
    service = HeatingCycleService(temp_delta_threshold=TARGET_MARGIN)
    history = _history(cycle_context["profile"], cycle_context)
    cycles = asyncio.run(
        service.extract_heating_cycles(
            DEVICE_ID, history, BASE_TIME, BASE_TIME + EXTRACTION_WINDOW
        )
    )
    cycle_context["cycles"] = cycles
    cycle_context["learned_dead_time"] = DeadTimeCalculationService().calculate_average_dead_time(
        cycles
    )
    cycle_context["learned_lhs"] = GlobalLHSCalculatorService().calculate_global_lhs(cycles)


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


def _single_cycle(cycle_context: dict[str, Any]) -> Any:
    cycles = cycle_context["cycles"]
    assert len(cycles) == 1, f"Expected one extracted cycle, got {len(cycles)}"
    return cycles[0]


@then(parsers.parse("the cycle has a dead time of {minutes:g} minutes"))
def cycle_dead_time(cycle_context: dict[str, Any], minutes: float) -> None:
    """THEN: the dead time is kept, however long."""
    assert _single_cycle(cycle_context).dead_time_cycle_minutes == pytest.approx(minutes)


@then("the cycle has no dead time")
def cycle_without_dead_time(cycle_context: dict[str, Any]) -> None:
    """THEN: the room never gained 0.2 °C, so the dead time is unknown."""
    assert _single_cycle(cycle_context).dead_time_cycle_minutes is None


@then(parsers.parse("the cycle has a heating slope of {slope:g} °C/h"))
def cycle_slope(cycle_context: dict[str, Any], slope: float) -> None:
    """THEN: the slope is the rise rate after the dead time."""
    assert _single_cycle(cycle_context).avg_heating_slope == pytest.approx(slope)


@then(parsers.parse("the learned dead time is {minutes:g} minutes"))
def learned_dead_time(cycle_context: dict[str, Any], minutes: float) -> None:
    """THEN: the cycle taught its dead time."""
    assert cycle_context["learned_dead_time"] == pytest.approx(minutes)


@then(parsers.parse("the learned heating slope is {slope:g} °C/h"))
def learned_slope(cycle_context: dict[str, Any], slope: float) -> None:
    """THEN: the cycle taught its heating slope, however slow."""
    assert cycle_context["learned_lhs"] == pytest.approx(slope)


@then("nothing is learned from the cycle")
def nothing_learned(cycle_context: dict[str, Any]) -> None:
    """THEN: no dead time is learned and the heating slope stays at its default."""
    assert cycle_context["cycles"], "The cycle should still have been extracted"
    assert cycle_context["learned_dead_time"] is None
    assert cycle_context["learned_lhs"] == DEFAULT_LEARNED_SLOPE
