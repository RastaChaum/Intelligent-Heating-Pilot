"""pytest-bdd step definitions for the environmental correction scenarios (#257).

Drives PredictionService with explicit daylight periods: the correction must leave
the dead time untouched and scale the solar gain by the share of the heating phase
spent between sunrise and sunset.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.domain.services import PredictionService
from custom_components.intelligent_heating_pilot.domain.value_objects import DaylightPeriod

scenarios("environmental_correction.feature")

DAY = datetime(2026, 11, 1, tzinfo=UTC)
START_TEMP = 18.0
SLOPE = 1.0  # °C/h: a heating phase of N minutes needs N / 60 °C
CLEAR_SKY = 0.0
OVERCAST_SKY = 100.0
TOLERANCE_MINUTES = 0.05


def _at(clock: str) -> datetime:
    hours, minutes = (int(part) for part in clock.split(":"))
    return DAY.replace(hour=hours, minute=minutes)


@pytest.fixture
def correction_context() -> dict:
    """Shared context: prediction inputs and results."""
    return {"humidity": None, "cloud_coverage": None, "daylight_periods": []}


@given(parsers.parse("the sun rises at {sunrise} and sets at {sunset}"))
def sun_times(correction_context: dict, sunrise: str, sunset: str) -> None:
    correction_context["daylight_periods"] = [DaylightPeriod(_at(sunrise), _at(sunset))]


@given("the sun position is unknown")
def sun_unknown(correction_context: dict) -> None:
    correction_context["daylight_periods"] = []


@given(
    parsers.parse(
        "a learned dead time of {dead_time:f} minutes and a heating phase of {heating:f} minutes"
    )
)
def dead_time_and_heating(correction_context: dict, dead_time: float, heating: float) -> None:
    correction_context["dead_time"] = dead_time
    correction_context["target_temp"] = START_TEMP + heating / 60.0 * SLOPE


@given(parsers.parse("the indoor humidity is {humidity:g} %"))
def indoor_humidity(correction_context: dict, humidity: float) -> None:
    correction_context["humidity"] = humidity


@given("the sky is clear")
def clear_sky(correction_context: dict) -> None:
    correction_context["cloud_coverage"] = CLEAR_SKY


def _anticipation(context: dict, cloud_coverage: float | None) -> float:
    prediction = PredictionService().predict_heating_time(
        current_temp=START_TEMP,
        target_temp=context["target_temp"],
        learned_slope=SLOPE,
        target_time=context["target_time"],
        humidity=context["humidity"],
        cloud_coverage=cloud_coverage,
        dead_time_minutes=context["dead_time"],
        daylight_periods=context["daylight_periods"],
    )
    return prediction.estimated_duration_minutes


@when(parsers.parse("IHP computes the anticipation for {clock}"))
def compute_anticipation(correction_context: dict, clock: str) -> None:
    correction_context["target_time"] = _at(clock)
    correction_context["anticipation"] = _anticipation(
        correction_context, correction_context["cloud_coverage"]
    )


@then(parsers.parse("the anticipation is {minutes:f} minutes"))
def anticipation_is(correction_context: dict, minutes: float) -> None:
    assert correction_context["anticipation"] == pytest.approx(minutes, abs=TOLERANCE_MINUTES)


@then("the anticipation is the same as under an overcast sky")
def same_as_overcast(correction_context: dict) -> None:
    overcast = _anticipation(correction_context, OVERCAST_SKY)
    assert correction_context["anticipation"] == pytest.approx(overcast)
