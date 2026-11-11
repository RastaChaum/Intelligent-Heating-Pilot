"""pytest-bdd step definitions for the Home Assistant startup scenarios.

While Home Assistant started, every scheduler or weather entity appearing triggered
a calculation, which only logged warnings as the thermostat was not readable yet.
Only Home Assistant and the orchestrator behind the bridge are replaced here, and
events go through the bridge's real listener.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import CoreState, State
from pytest_bdd import given, scenarios, then, when

from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import HAEventBridge

scenarios("ha_startup.feature")

VTHERM_ENTITY_ID = "climate.living_room"
SCHEDULER_ENTITY_ID = "switch.schedule_living_room"
ROOM_TEMPERATURE = 19.5
ANTICIPATION_EVENT = "intelligent_heating_pilot_anticipation_calculated"
BRIDGE_MODULE = "custom_components.intelligent_heating_pilot.infrastructure.event_bridge"


def _run_to_completion(coroutine: Coroutine[Any, Any, None]) -> Mock:
    """Stand in for hass.async_create_task, finishing the task before the next step."""
    asyncio.run(coroutine)
    task = Mock()
    task.done.return_value = True
    return task


class Startup:
    """A Home Assistant startup: its state machine, and IHP's bridge listening to it."""

    def __init__(self) -> None:
        self.states: dict[str, State] = {}
        self.orchestrator = AsyncMock()
        self.orchestrator.calculate_and_schedule_anticipation.return_value = {}

        self.hass = Mock()
        self.hass.state = CoreState.not_running
        self.hass.async_create_task.side_effect = _run_to_completion
        self.bridge = HAEventBridge(
            self.hass, self.orchestrator, VTHERM_ENTITY_ID, [SCHEDULER_ENTITY_ID]
        )
        with patch(f"{BRIDGE_MODULE}.async_track_state_change_event") as track:
            self.bridge.setup_listeners()
        self._on_entity_changed: Callable[[Mock], None] = track.call_args.args[2]

    def set_state(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        """Write a state and deliver its state change event, as Home Assistant does."""
        old_state = self.states.get(entity_id)
        new_state = State(entity_id, state, attributes or {})
        self.states[entity_id] = new_state
        event = Mock()
        event.data = {"entity_id": entity_id, "old_state": old_state, "new_state": new_state}
        self._on_entity_changed(event)


@pytest.fixture
def startup() -> Startup:
    """Return the startup under test."""
    return Startup()


# ------------------------------------------------------------------
# Given
# ------------------------------------------------------------------


@given("Home Assistant is starting")
def ha_starting(startup: Startup) -> None:
    """GIVEN: Starting, the state in which is_running would already be true."""
    startup.hass.state = CoreState.starting


@given("the thermostat exists without a room temperature")
def thermostat_without_temperature(startup: Startup) -> None:
    """GIVEN: The VTherm entity exists but has not read its sensors yet."""
    startup.set_state(VTHERM_ENTITY_ID, "heat", {"current_temperature": None})


# ------------------------------------------------------------------
# Given or When
# ------------------------------------------------------------------


@given("Home Assistant has started")
@when("Home Assistant has started")
def ha_started(startup: Startup) -> None:
    """Home Assistant has finished starting."""
    startup.hass.state = CoreState.running


@given("a scheduler entity appears")
@when("a scheduler entity appears")
def scheduler_appears(startup: Startup) -> None:
    """A scheduler entity is created, which always counts as a meaningful change."""
    startup.set_state(SCHEDULER_ENTITY_ID, "on")


# ------------------------------------------------------------------
# When
# ------------------------------------------------------------------


@when("the thermostat reports a room temperature")
def thermostat_reports(startup: Startup) -> None:
    """WHEN: The VTherm has read its sensors."""
    startup.set_state(VTHERM_ENTITY_ID, "heat", {"current_temperature": ROOM_TEMPERATURE})


@when("the startup update runs")
def startup_update_runs(startup: Startup) -> None:
    """WHEN: The staggered update requests the publication the sensors wait for."""
    startup.bridge.request_forced_publish()


# ------------------------------------------------------------------
# Then
# ------------------------------------------------------------------


@then("no anticipation is calculated")
def no_calculation(startup: Startup) -> None:
    """THEN: The orchestrator was never called, so nothing read missing data."""
    startup.orchestrator.calculate_and_schedule_anticipation.assert_not_called()


@then("one anticipation is calculated")
def one_calculation(startup: Startup) -> None:
    """THEN: A single calculation covers everything that happened before."""
    startup.orchestrator.calculate_and_schedule_anticipation.assert_awaited_once()


@then("the sensors are updated")
def sensors_updated(startup: Startup) -> None:
    """THEN: The event the sensors listen to was fired."""
    startup.hass.bus.async_fire.assert_called_once()
    assert startup.hass.bus.async_fire.call_args.args[0] == ANTICIPATION_EVENT
