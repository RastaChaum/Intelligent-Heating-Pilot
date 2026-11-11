"""pytest-bdd step definitions for a preheat starting before midnight (#250).

HACS Scheduler's ``run_action`` receives only a time and looks for the
timeslot at that time on the day it is called. These steps wire the real
orchestrator, use cases and HA scheduler adapters against a mock ``hass``
whose ``scheduler.run_action`` mirrors scheduler-component: it applies the
slot only when the schedule runs on today's weekday and its conditions hold.
Timers are recorded instead of being scheduled, so a scenario can fire the
planned retry itself.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.application.orchestrator import (
    HeatingOrchestrator,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
    UpdateCacheDataUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import ITimerScheduler
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HAClimateDataReader,
    HASchedulerCommander,
    HASchedulerReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

scenarios("cross_midnight_preheat.feature")

_CLIMATE_READER_MODULE = (
    "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader"
)
# Keeps the blocked scenarios fast; the production wait is ACTION_EFFECT_TIMEOUT_SECONDS.
_ACTION_EFFECT_TIMEOUT_SECONDS = 0.05
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAYS_TO_SEARCH = 8


class _RecordingTimerScheduler(ITimerScheduler):
    """Records timers instead of scheduling them, keeping track of cancellations."""

    def __init__(self) -> None:
        self.timers: list[dict] = []

    def schedule_timer(self, target_time: datetime, callback_func) -> object:
        timer = {"time": target_time, "callback": callback_func, "cancelled": False}
        self.timers.append(timer)

        def _cancel() -> None:
            timer["cancelled"] = True

        return _cancel

    def active_timers(self) -> list[dict]:
        return [timer for timer in self.timers if not timer["cancelled"]]


@pytest.fixture
def midnight_context() -> dict:
    """Shared context for the cross-midnight BDD scenarios."""
    return {
        "states": {},
        "scheduler_ids": [],
        "schedules": {},
        "blocked_by_conditions": set(),
        "service_calls": [],
        "state_listeners": [],
        "anticipation": timedelta(hours=6),
    }


@pytest.fixture(autouse=True)
def _restore_time_zone():
    """Restore HA's default time zone changed by the Background."""
    original = dt_util.DEFAULT_TIME_ZONE
    yield
    dt_util.set_default_time_zone(original)


def _make_state(entity_id: str, state_value: str, attributes: dict) -> Mock:
    state = Mock()
    state.entity_id = entity_id
    state.state = state_value
    state.attributes = attributes
    return state


@given(parsers.parse('the home is in the "{tz_name}" time zone'))
def home_time_zone(midnight_context: dict, tz_name: str) -> None:
    """GIVEN: HA's local time zone, which scheduler-component uses for "today"."""
    midnight_context["tz"] = ZoneInfo(tz_name)
    dt_util.set_default_time_zone(midnight_context["tz"])


@given(parsers.parse('the thermostat "{entity_id}" currently targets {temp:f}°C'))
def thermostat_current_target(midnight_context: dict, entity_id: str, temp: float) -> None:
    """GIVEN: The thermostat holds its current target temperature."""
    midnight_context["vtherm_id"] = entity_id
    midnight_context["states"][entity_id] = _make_state(entity_id, "heat", {"temperature": temp})


@given(parsers.parse("IHP anticipates each slot {hours:d} hours ahead"))
def anticipation_duration(midnight_context: dict, hours: int) -> None:
    """GIVEN: A slow room, whose preheat starts long before the slot."""
    midnight_context["anticipation"] = timedelta(hours=hours)


@given(
    parsers.parse(
        'a HACS scheduler "{entity_id}" running on "{days}" with a timeslot at '
        "{time} for {temp:f}°C"
    )
)
def hacs_scheduler(midnight_context: dict, entity_id: str, days: str, time: str, temp: float):
    """GIVEN: A HACS Scheduler switch running on some weekdays, with one comfort timeslot."""
    hour, minute = (int(part) for part in time.split(":"))
    weekdays = {_WEEKDAYS.index(day.strip()) for day in days.split(",")}
    midnight_context["scheduler_ids"].append(entity_id)
    midnight_context["schedules"][entity_id] = {
        "weekdays": weekdays,
        "hour": hour,
        "minute": minute,
        "temp": temp,
    }
    midnight_context["states"][entity_id] = _make_state(entity_id, "on", {})


@given(parsers.parse('"{entity_id}" is blocked by its own conditions when triggered'))
def scheduler_blocked_by_conditions(midnight_context: dict, entity_id: str) -> None:
    """GIVEN: This scheduler's own conditions will not hold when run_action fires."""
    midnight_context["blocked_by_conditions"].add(entity_id)


@given(parsers.parse("it is {weekday} {date} {time}"))
def current_time(midnight_context: dict, weekday: str, date: str, time: str) -> None:
    """GIVEN: The local date and time at which IHP recalculates."""
    now = datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=midnight_context["tz"])
    assert now.strftime("%A") == weekday, f"{date} is a {now.strftime('%A')}"
    midnight_context["now"] = now


def _next_slot(schedule: dict, now: datetime) -> datetime:
    """Next occurrence of a schedule's timeslot strictly after ``now``."""
    for days_ahead in range(_DAYS_TO_SEARCH):
        candidate = (now + timedelta(days=days_ahead)).replace(
            hour=schedule["hour"], minute=schedule["minute"], second=0, microsecond=0
        )
        if candidate > now and candidate.weekday() in schedule["weekdays"]:
            return candidate
    raise AssertionError("schedule has no upcoming timeslot")


def _run_action(midnight_context: dict, entity_id: str, time_str: str) -> None:
    """Mirror scheduler-component's run_action: the time is applied to today's date."""
    schedule = midnight_context["schedules"][entity_id]
    now = midnight_context["now"]
    runs_today = now.weekday() in schedule["weekdays"]
    is_slot_time = time_str == f"{schedule['hour']:02d}:{schedule['minute']:02d}"
    if not runs_today or not is_slot_time:
        return  # "Schedule ... has no active timeslot at HH:MM"
    if entity_id in midnight_context["blocked_by_conditions"]:
        return  # Conditions unmet: scheduler-component withholds the action
    midnight_context["states"][midnight_context["vtherm_id"]].attributes["temperature"] = schedule[
        "temp"
    ]
    for listener in list(midnight_context["state_listeners"]):
        listener(Mock())


def _make_hass(midnight_context: dict) -> Mock:
    hass = Mock()
    hass.is_running = True
    hass.states.get.side_effect = midnight_context["states"].get

    async def _async_call(domain: str, service: str, data: dict, blocking: bool = True) -> None:
        midnight_context["service_calls"].append(dict(data))
        if domain == "scheduler" and service == "run_action":
            _run_action(midnight_context, data["entity_id"], data["time"])

    hass.services.async_call = AsyncMock(side_effect=_async_call)
    return hass


def _make_state_change_tracker(midnight_context: dict):
    """Stand-in for HA's async_track_state_change_event, fed by _run_action."""

    def _track(_hass: Mock, entity_ids: list[str], action):
        assert entity_ids == [midnight_context["vtherm_id"]]
        midnight_context["state_listeners"].append(action)
        return lambda: midnight_context["state_listeners"].remove(action)

    return _track


class _FakeCalculateAnticipation:
    """Stand-in for CalculateAnticipationUseCase.

    Picks the earliest upcoming timeslot among the non-excluded schedulers and
    starts its preheat a fixed duration ahead, without the LHS pipeline the
    scenarios do not exercise.
    """

    def __init__(self, midnight_context: dict) -> None:
        self._context = midnight_context

    async def calculate_anticipation_datas(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> dict:
        now = self._context["now"]
        slots = [
            (_next_slot(self._context["schedules"][entity_id], now), entity_id)
            for entity_id in self._context["scheduler_ids"]
            if entity_id not in exclude_entity_ids
        ]
        if not slots:
            return {"anticipated_start_time": None, "scheduler_entity": None}
        target_time, scheduler_entity = min(slots)
        return {
            "anticipated_start_time": target_time - self._context["anticipation"],
            "next_schedule_time": target_time,
            "next_target_temperature": self._context["schedules"][scheduler_entity]["temp"],
            "scheduler_entity": scheduler_entity,
            "learned_heating_slope": 0.5,
            "current_temp": 17.0,
            "anticipation_minutes": int(self._context["anticipation"].total_seconds() // 60),
        }


def _build_orchestrator(midnight_context: dict) -> HeatingOrchestrator:
    hass = _make_hass(midnight_context)
    scheduler_commander = HASchedulerCommander(hass)
    climate_data_reader = HAClimateDataReader(
        hass, RecorderAccessQueue(), midnight_context["vtherm_id"]
    )
    control_preheating = ControlPreheatingUseCase(
        scheduler_commander,
        climate_data_reader=climate_data_reader,
        action_effect_timeout_seconds=_ACTION_EFFECT_TIMEOUT_SECONDS,
    )
    timer_scheduler = _RecordingTimerScheduler()
    schedule_anticipation_action = ScheduleAnticipationActionUseCase(
        scheduler_reader=HASchedulerReader(hass, midnight_context["scheduler_ids"]),
        scheduler_commander=scheduler_commander,
        timer_scheduler=timer_scheduler,
        control_preheating_use_case=control_preheating,
    )
    orchestrator = HeatingOrchestrator(
        calculate_anticipation=_FakeCalculateAnticipation(midnight_context),
        control_preheating=control_preheating,
        schedule_anticipation_action=schedule_anticipation_action,
        update_cache=Mock(spec=UpdateCacheDataUseCase),
    )
    schedule_anticipation_action.set_on_scheduler_blocked(
        orchestrator.retry_anticipation_after_blocked_scheduler
    )
    midnight_context["control_preheating"] = control_preheating
    midnight_context["timer_scheduler"] = timer_scheduler
    return orchestrator


def _run_at_current_time(midnight_context: dict, coroutine_factory):
    """Run a coroutine with HA's clock and the thermostat listener patched."""

    async def _run():
        with (
            patch.object(dt_util, "now", side_effect=lambda *_: midnight_context["now"]),
            patch(
                f"{_CLIMATE_READER_MODULE}.async_track_state_change_event",
                side_effect=_make_state_change_tracker(midnight_context),
            ),
        ):
            return await coroutine_factory()

    return asyncio.run(_run())


@when("IHP recalculates and schedules anticipation")
def recalculate_and_schedule(midnight_context: dict) -> None:
    """WHEN: The orchestrator runs one full calculate+schedule cycle."""
    orchestrator = _build_orchestrator(midnight_context)
    midnight_context["result"] = _run_at_current_time(
        midnight_context,
        lambda: orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True),
    )


@when("the planned retry fires")
def planned_retry_fires(midnight_context: dict) -> None:
    """WHEN: HA fires the single pending timer at its planned time."""
    (timer,) = midnight_context["timer_scheduler"].active_timers()
    midnight_context["now"] = timer["time"]
    timer["cancelled"] = True  # A fired point-in-time listener is spent
    _run_at_current_time(midnight_context, timer["callback"])


@then(parsers.parse('a retry of "{entity_id}" is planned at {date} {time}'))
def retry_planned(midnight_context: dict, entity_id: str, date: str, time: str) -> None:
    """THEN: The scheduler was already tried once, and one timer waits for after midnight."""
    expected = datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=midnight_context["tz"])
    triggered = [call["entity_id"] for call in midnight_context["service_calls"]]
    assert triggered == [entity_id]
    timers = midnight_context["timer_scheduler"].active_timers()
    assert [timer["time"] for timer in timers] == [expected]


@then("no retry is planned")
def no_retry_planned(midnight_context: dict) -> None:
    """THEN: No timer is pending."""
    assert midnight_context["timer_scheduler"].active_timers() == []


@then(parsers.parse('IHP is preheating for "{entity_id}"'))
def preheating_for(midnight_context: dict, entity_id: str) -> None:
    """THEN: The preheat is confirmed and tracked for this scheduler."""
    assert midnight_context["control_preheating"].is_preheating_active() is True
    assert midnight_context["control_preheating"].get_active_scheduler_entity() == entity_id


@then(parsers.parse('"{entity_id}" is never triggered'))
def never_triggered(midnight_context: dict, entity_id: str) -> None:
    """THEN: IHP sent no scheduler action for this entity."""
    triggered = [call["entity_id"] for call in midnight_context["service_calls"]]
    assert entity_id not in triggered


@then("no scheduler is reported blocked this cycle")
def no_scheduler_blocked(midnight_context: dict) -> None:
    """THEN: Neither the cycle nor any scheduler is reported blocked."""
    assert midnight_context["result"]["blocked_schedulers"] == []
    assert midnight_context["result"]["scheduler_blocked"] is False


@then(parsers.parse('the blocked schedulers for this cycle are "{entity_ids}"'))
def blocked_schedulers_are(midnight_context: dict, entity_ids: str) -> None:
    """THEN: blocked_schedulers lists exactly the expected entities, in order."""
    expected = [entity_id.strip() for entity_id in entity_ids.split(",")]
    assert midnight_context["result"]["blocked_schedulers"] == expected


@then(parsers.parse("the room's target temperature becomes {temp:f}°C"))
def room_target_becomes(midnight_context: dict, temp: float) -> None:
    """THEN: The VTherm's target temperature reflects a successful trigger."""
    vtherm_state = midnight_context["states"][midnight_context["vtherm_id"]]
    assert vtherm_state.attributes["temperature"] == temp


@then(parsers.parse("the room's target temperature stays at {temp:f}°C"))
def room_target_stays(midnight_context: dict, temp: float) -> None:
    """THEN: No scheduler action was applied; the thermostat is untouched."""
    vtherm_state = midnight_context["states"][midnight_context["vtherm_id"]]
    assert vtherm_state.attributes["temperature"] == temp
