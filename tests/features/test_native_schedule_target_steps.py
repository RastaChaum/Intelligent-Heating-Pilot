"""pytest-bdd step definitions for the native schedule target temperature (#188).

A native ``schedule.*`` entity only tells when the next ON slot starts, not which
temperature it applies. While the schedule is off, the thermostat holds its
off-period setpoint, so IHP must anticipate the comfort preset instead.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.util import dt as dt_util
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.use_cases.control_preheating_use_case import (
    ControlPreheatingUseCase,
)
from custom_components.intelligent_heating_pilot.application.use_cases.schedule_anticipation_action_use_case import (
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
)
from tests.actuator_helpers import build_hacs_router

scenarios("native_schedule_target.feature")

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_COMFORT_TEMP = 21.0
_MINUTES_UNTIL_SLOT = 30
_ANTICIPATION_MINUTES = 45


class _ServiceNotFoundError(Exception):
    """Stand-in for Home Assistant's ServiceNotFound (HACS Scheduler absent)."""


@pytest.fixture
def schedule_context() -> dict:
    """Shared context for native schedule BDD scenarios."""
    return {"states": {}}


def _make_state(entity_id: str, state_value: str, attributes: dict) -> Mock:
    state = Mock()
    state.entity_id = entity_id
    state.state = state_value
    state.attributes = attributes
    return state


@given(
    parsers.parse('a native schedule "{entity_id}" that is off with its next ON event at {time}')
)
def native_schedule_off(schedule_context: dict, entity_id: str, time: str) -> None:
    """GIVEN: A native schedule outside its active block, whose blocks start at ``time``.

    The schedule is read through ``schedule.get_schedule``, so every weekday carries the block.
    """
    schedule_context["schedule_id"] = entity_id
    schedule_context["states"][entity_id] = _make_state(
        entity_id, "off", {"friendly_name": "Heating"}
    )
    block = {"from": f"{time}:00", "to": "09:00:00"}
    schedule_context["schedule_response"] = {entity_id: {day: [block] for day in _WEEKDAYS}}


@given(parsers.parse('the thermostat "{entity_id}" currently targets {temp:f}°C'))
def thermostat_current_target(schedule_context: dict, entity_id: str, temp: float) -> None:
    """GIVEN: The thermostat holds its off-period (eco) setpoint."""
    schedule_context["vtherm_id"] = entity_id
    schedule_context["states"][entity_id] = _make_state(
        entity_id, "heat", {"temperature": temp, "preset_mode": "eco"}
    )


@given(parsers.parse("the thermostat comfort preset is {temp:f}°C"))
def thermostat_comfort_preset(schedule_context: dict, temp: float) -> None:
    """GIVEN: The VTherm exposes its comfort preset temperature."""
    vtherm_state = schedule_context["states"][schedule_context["vtherm_id"]]
    vtherm_state.attributes["preset_temperatures"] = {"eco_temp": 17.0, "comfort_temp": temp}


@given("the thermostat comfort preset is not initialized")
def thermostat_comfort_preset_uninitialized(schedule_context: dict) -> None:
    """GIVEN: The VTherm reports 0°C for comfort, its value for an unset preset."""
    vtherm_state = schedule_context["states"][schedule_context["vtherm_id"]]
    vtherm_state.attributes["preset_temperatures"] = {"eco_temp": 17.0, "comfort_temp": 0}
    vtherm_state.attributes["comfort_temp"] = 0


@given("HACS Scheduler is not installed")
def hacs_scheduler_not_installed(schedule_context: dict) -> None:
    """GIVEN: Any scheduler service call fails as the service does not exist."""
    schedule_context["services"] = AsyncMock(side_effect=_ServiceNotFoundError("scheduler"))


def _make_hass(schedule_context: dict) -> Mock:
    hass = Mock()
    hass.is_running = True
    hass.states.get.side_effect = schedule_context["states"].get
    scheduler_services = schedule_context.setdefault("services", AsyncMock())

    async def _async_call(domain: str, service: str, data: dict | None = None, **kwargs):
        """Answer the schedule helper's get_schedule; any other service is a scheduler call."""
        if domain == "schedule":
            return schedule_context["schedule_response"]
        return await scheduler_services(domain, service, data, **kwargs)

    hass.services.async_call = _async_call
    return hass


def _make_reader(schedule_context: dict) -> HASchedulerReader:
    return HASchedulerReader(
        _make_hass(schedule_context),
        [schedule_context["schedule_id"]],
        climate_entity_id=schedule_context["vtherm_id"],
    )


def _make_action_use_case(schedule_context: dict) -> ScheduleAnticipationActionUseCase:
    """Wire the real anticipation use cases with the real HA scheduler adapters."""
    control = ControlPreheatingUseCase(build_hacs_router(_make_hass(schedule_context)))
    schedule_context["control"] = control
    timer_scheduler = Mock()
    timer_scheduler.schedule_timer.side_effect = lambda _when, callback: schedule_context.update(
        timer_callback=callback
    )
    return ScheduleAnticipationActionUseCase(
        scheduler_reader=_make_reader(schedule_context),
        timer_scheduler=timer_scheduler,
        control_preheating_use_case=control,
    )


def _anticipation_data(schedule_context: dict, anticipated_start: datetime) -> dict:
    return {
        "anticipated_start_time": anticipated_start,
        "next_schedule_time": schedule_context["slot_time"],
        "next_target_temperature": _COMFORT_TEMP,
        "anticipation_minutes": _ANTICIPATION_MINUTES,
        "scheduler_entity": schedule_context["schedule_id"],
        "learned_heating_slope": 2.0,
        "current_temp": 17.0,
    }


@when("IHP reads the next scheduled timeslot")
def read_next_timeslot(schedule_context: dict) -> None:
    """WHEN: The scheduler reader resolves the next timeslot."""
    reader = _make_reader(schedule_context)
    schedule_context["timeslot"] = asyncio.run(reader.get_next_timeslot())


@when("IHP recalculates twice inside the preheating window of the native schedule")
def recalculate_in_preheating_window(schedule_context: dict) -> None:
    """WHEN: The anticipated start is already past and the slot is still ahead."""
    schedule_context["slot_time"] = dt_util.now() + timedelta(minutes=_MINUTES_UNTIL_SLOT)
    anticipated_start = schedule_context["slot_time"] - timedelta(minutes=_ANTICIPATION_MINUTES)
    use_case = _make_action_use_case(schedule_context)
    data = _anticipation_data(schedule_context, anticipated_start)

    async def _recalculate_twice() -> None:
        await use_case.handle_anticipation_scheduling(data, ihp_enabled=True)
        await use_case.handle_anticipation_scheduling(data, ihp_enabled=True)

    asyncio.run(_recalculate_twice())


@when("the anticipation timer fires for the native schedule")
def anticipation_timer_fires(schedule_context: dict) -> None:
    """WHEN: The anticipated start is ahead, a timer is set and then fires."""
    schedule_context["slot_time"] = dt_util.now() + timedelta(hours=2)
    anticipated_start = schedule_context["slot_time"] - timedelta(minutes=_ANTICIPATION_MINUTES)
    use_case = _make_action_use_case(schedule_context)
    data = _anticipation_data(schedule_context, anticipated_start)

    async def _schedule_then_fire() -> None:
        await use_case.handle_anticipation_scheduling(data, ihp_enabled=True)
        await schedule_context["timer_callback"]()

    asyncio.run(_schedule_then_fire())


@then(parsers.parse("the timeslot starts at {time}"))
def timeslot_starts_at(schedule_context: dict, time: str) -> None:
    """THEN: The timeslot starts at the native schedule next ON event."""
    timeslot = schedule_context["timeslot"]
    assert timeslot is not None
    assert timeslot.target_time.strftime("%H:%M") == time


@then(parsers.parse("the timeslot target temperature is {temp:f}°C"))
def timeslot_target_temperature(schedule_context: dict, temp: float) -> None:
    """THEN: The timeslot targets the expected comfort temperature."""
    timeslot = schedule_context["timeslot"]
    assert timeslot is not None
    assert timeslot.target_temp == temp


@then("no scheduler service is called")
def no_scheduler_service_called(schedule_context: dict) -> None:
    """THEN: IHP did not try to drive the heating through HACS Scheduler."""
    schedule_context["services"].assert_not_called()


@then("IHP tracks the preheating of the native schedule slot as started")
def preheating_tracked_as_started(schedule_context: dict) -> None:
    """THEN: The preheat is marked started, so later recalculations do not retry it."""
    control = schedule_context["control"]
    assert control.is_preheating_active() is True
    assert control.get_preheating_target_time() == schedule_context["slot_time"]
