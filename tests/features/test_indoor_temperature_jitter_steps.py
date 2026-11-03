"""pytest-bdd step definitions for indoor temperature jitter scenarios (#258).

A room sensor toggling between two adjacent values moved the pending preheat
start back and forth, and a higher reading just before the timer fired made the
preheat start late. IHP now reads the VTherm smoothed temperature (``ema_temp``)
for the anticipation, and only a change of that temperature triggers a
recalculation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader import (
    HAEnvironmentReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
)

scenarios("indoor_temperature_jitter.feature")

VTHERM_ENTITY_ID = "climate.living_room"


def _vtherm_state(reading: float, smoothed: float | None) -> State:
    attributes: dict[str, float] = {"current_temperature": reading}
    if smoothed is not None:
        attributes["ema_temp"] = smoothed
    return State(VTHERM_ENTITY_ID, "heat", attributes)


def _parse_values(values: str) -> list[float]:
    return [float(value) for value in values.split(",")]


@pytest.fixture
def jitter_context() -> dict:
    """Shared context: the thermostat state, the bridge and the results."""
    return {}


# ------------------------------------------------------------------
# Given
# ------------------------------------------------------------------


@given(
    parsers.parse(
        "the thermostat reads {reading:f} °C with a smoothed temperature of {smoothed:f} °C"
    )
)
def thermostat_with_smoothed(jitter_context: dict, reading: float, smoothed: float) -> None:
    """GIVEN: The VTherm publishes a raw reading and its moving average."""
    jitter_context["state"] = _vtherm_state(reading, smoothed)


@given(parsers.parse("the thermostat reads {reading:f} °C with no smoothed temperature"))
def thermostat_without_smoothed(jitter_context: dict, reading: float) -> None:
    """GIVEN: The thermostat publishes only its raw reading."""
    jitter_context["state"] = _vtherm_state(reading, None)


@given("IHP monitors the thermostat")
def ihp_monitors_thermostat(jitter_context: dict) -> None:
    """GIVEN: The event bridge listens to the thermostat."""
    bridge = HAEventBridge(
        hass=Mock(),
        orchestrator=AsyncMock(),
        vtherm_entity_id=VTHERM_ENTITY_ID,
        scheduler_entity_ids=[],
    )
    bridge._request_recalculate = Mock()  # type: ignore[method-assign]
    jitter_context["bridge"] = bridge


# ------------------------------------------------------------------
# When
# ------------------------------------------------------------------


@when("IHP reads the current environment")
def read_environment(jitter_context: dict) -> None:
    """WHEN: IHP reads the environment it anticipates from."""
    hass = Mock()
    hass.states.get = Mock(side_effect={VTHERM_ENTITY_ID: jitter_context["state"]}.get)
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters."
        "environment_reader.get_entity_name",
        return_value="Living Room",
    ):
        reader = HAEnvironmentReader(hass, VTHERM_ENTITY_ID)
    jitter_context["environment"] = asyncio.run(reader.get_current_environment())


def _replay(jitter_context: dict, states: list[State]) -> None:
    """Feed consecutive thermostat states to the bridge, recording each trigger."""
    recalculate = jitter_context["bridge"]._request_recalculate
    triggers = []
    for old_state, new_state in zip(states, states[1:], strict=False):
        recalculate.reset_mock()
        event = Mock(
            data={"entity_id": VTHERM_ENTITY_ID, "old_state": old_state, "new_state": new_state}
        )
        jitter_context["bridge"]._handle_vtherm_change(event)
        triggers.append(recalculate.called)
    jitter_context["triggers"] = triggers


@when(
    parsers.parse("the thermostat reads {values} °C with a smoothed temperature of {smoothed:f} °C")
)
def thermostat_reading_toggles(jitter_context: dict, values: str, smoothed: float) -> None:
    """WHEN: The raw reading toggles while the moving average stays put."""
    _replay(jitter_context, [_vtherm_state(v, smoothed) for v in _parse_values(values)])


@when(
    parsers.parse(
        "the smoothed temperature goes {values} °C while the thermostat reads {reading:f} °C"
    )
)
def smoothed_temperature_moves(jitter_context: dict, values: str, reading: float) -> None:
    """WHEN: The moving average moves while the raw reading stays put."""
    _replay(jitter_context, [_vtherm_state(reading, v) for v in _parse_values(values)])


# ------------------------------------------------------------------
# Then
# ------------------------------------------------------------------


@then(parsers.parse("the room temperature is {expected:f} °C"))
def room_temperature_is(jitter_context: dict, expected: float) -> None:
    """THEN: The anticipation sees this room temperature."""
    assert jitter_context["environment"].indoor_temperature == pytest.approx(expected)


@then("no step triggers a recalculation")
def no_step_triggers(jitter_context: dict) -> None:
    """THEN: The pending preheat timer is left where it is."""
    assert jitter_context["triggers"]
    assert not any(jitter_context["triggers"])


@then("every step triggers a recalculation")
def every_step_triggers(jitter_context: dict) -> None:
    """THEN: The anticipation follows the room's trend."""
    assert jitter_context["triggers"]
    assert all(jitter_context["triggers"])
