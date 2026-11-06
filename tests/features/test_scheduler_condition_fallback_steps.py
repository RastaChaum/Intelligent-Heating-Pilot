"""pytest-bdd step definitions for the scheduler-condition fallback (#64).

A household with several scheduler entities (e.g. a vacation calendar and a
non-vacation calendar) must still heat on time through whichever scheduler can
actually act, instead of waiting for a blocked scheduler's own slot time to
elapse. These steps wire the real orchestrator, use cases, and HA scheduler
adapters against a mock ``hass`` whose service-call side effect simulates the
HACS Scheduler integration: it only applies the climate change for schedulers
that are not marked "blocked by its own conditions" in the scenario.

Since #256 the thermostat can also apply the action a moment after
``run_action`` has returned, as scheduler-component does: IHP must wait for the
thermostat's state change before reporting the scheduler blocked.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

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
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HAClimateDataReader,
    HASchedulerCommander,
    HASchedulerReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

scenarios("scheduler_condition_fallback.feature")

_CLIMATE_READER_MODULE = (
    "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader"
)
# Keeps the blocked scenarios fast; the production wait is ACTION_EFFECT_TIMEOUT_SECONDS.
_ACTION_EFFECT_TIMEOUT_SECONDS = 0.05

_TODAY = "2024-01-15"
_TZ = "+01:00"


@pytest.fixture
def fallback_context() -> dict:
    """Shared context for the scheduler-condition-fallback BDD scenarios."""
    return {
        "states": {},
        "scheduler_ids": [],
        "slot_by_scheduler": {},
        "blocked_by_conditions": set(),
        "service_calls": [],
        "delayed_apply": False,
        "state_listeners": [],
    }


def _make_state(entity_id: str, state_value: str, attributes: dict) -> Mock:
    state = Mock()
    state.entity_id = entity_id
    state.state = state_value
    state.attributes = attributes
    return state


@given(parsers.parse('the thermostat "{entity_id}" currently targets {temp:f}°C'))
def thermostat_current_target(fallback_context: dict, entity_id: str, temp: float) -> None:
    """GIVEN: The thermostat holds its current target temperature."""
    fallback_context["vtherm_id"] = entity_id
    fallback_context["states"][entity_id] = _make_state(entity_id, "heat", {"temperature": temp})


@given(
    parsers.parse('a HACS scheduler "{entity_id}" with its next timeslot at {time} for {temp:f}°C')
)
def hacs_scheduler(fallback_context: dict, entity_id: str, time: str, temp: float) -> None:
    """GIVEN: A HACS Scheduler switch entity with one upcoming timeslot."""
    fallback_context["scheduler_ids"].append(entity_id)
    fallback_context["slot_by_scheduler"][entity_id] = (time, temp)
    fallback_context["states"][entity_id] = _make_state(
        entity_id,
        "on",
        {
            "next_trigger": f"{_TODAY}T{time}:00{_TZ}",
            "next_slot": 0,
            "actions": [{"service": "climate.set_temperature", "data": {"temperature": temp}}],
        },
    )


@given("the thermostat applies a triggered action a moment after run_action returns")
def thermostat_applies_with_delay(fallback_context: dict) -> None:
    """GIVEN: scheduler-component returns before the climate entity has changed (#256)."""
    fallback_context["delayed_apply"] = True


@given(parsers.parse('"{entity_id}" is blocked by its own conditions when triggered'))
def scheduler_blocked_by_conditions(fallback_context: dict, entity_id: str) -> None:
    """GIVEN: This scheduler's own conditions will not hold when run_action fires."""
    fallback_context["blocked_by_conditions"].add(entity_id)


def _make_hass(fallback_context: dict) -> Mock:
    hass = Mock()
    hass.is_running = True
    hass.states.get.side_effect = fallback_context["states"].get

    async def _async_call(domain: str, service: str, data: dict, blocking: bool = True) -> None:
        fallback_context["service_calls"].append(dict(data))
        if domain != "scheduler" or service != "run_action":
            return
        entity_id = data["entity_id"]
        if entity_id in fallback_context["blocked_by_conditions"]:
            return  # Simulate scheduler-component withholding the action (conditions unmet)
        _, target_temp = fallback_context["slot_by_scheduler"][entity_id]
        if fallback_context["delayed_apply"]:
            asyncio.get_running_loop().call_soon(_apply_target, fallback_context, target_temp)
        else:
            _apply_target(fallback_context, target_temp)

    hass.services.async_call = AsyncMock(side_effect=_async_call)
    return hass


def _apply_target(fallback_context: dict, target_temp: float) -> None:
    """Set the thermostat's target and notify its state change listeners."""
    fallback_context["states"][fallback_context["vtherm_id"]].attributes["temperature"] = (
        target_temp
    )
    for listener in list(fallback_context["state_listeners"]):
        listener(Mock())


def _make_state_change_tracker(fallback_context: dict):
    """Stand-in for HA's async_track_state_change_event, fed by _apply_target."""

    def _track(_hass: Mock, entity_ids: list[str], action):
        assert entity_ids == [fallback_context["vtherm_id"]]
        fallback_context["state_listeners"].append(action)
        return lambda: fallback_context["state_listeners"].remove(action)

    return _track


class _FakeCalculateAnticipation:
    """Stand-in for CalculateAnticipationUseCase.

    Returns canned anticipation data keyed by the earliest non-excluded
    configured scheduler, mirroring what the real use case would compute from
    HASchedulerReader.get_next_timeslot(exclude_entity_ids=...) without
    requiring the full LHS/prediction pipeline the BDD scenario does not
    exercise.
    """

    def __init__(self, fallback_context: dict) -> None:
        self._context = fallback_context

    async def calculate_anticipation_datas(
        self, exclude_entity_ids: frozenset[str] = frozenset()
    ) -> dict:
        candidates = [
            entity_id
            for entity_id in self._context["scheduler_ids"]
            if entity_id not in exclude_entity_ids
        ]
        if not candidates:
            return {"anticipated_start_time": None, "scheduler_entity": None}

        scheduler_entity = sorted(
            candidates, key=lambda e: self._context["slot_by_scheduler"][e][0]
        )[0]
        time_str, target_temp = self._context["slot_by_scheduler"][scheduler_entity]
        target_time = datetime.fromisoformat(f"{_TODAY}T{time_str}:00{_TZ}")
        return {
            "anticipated_start_time": target_time - timedelta(minutes=5),
            "next_schedule_time": target_time,
            "next_target_temperature": target_temp,
            "scheduler_entity": scheduler_entity,
            "learned_heating_slope": 2.0,
            "current_temp": 17.0,
        }


def _build_orchestrator(fallback_context: dict) -> HeatingOrchestrator:
    hass = _make_hass(fallback_context)
    scheduler_commander = HASchedulerCommander(hass)
    climate_data_reader = HAClimateDataReader(
        hass, RecorderAccessQueue(), fallback_context["vtherm_id"]
    )
    control_preheating = ControlPreheatingUseCase(
        scheduler_commander,
        climate_data_reader=climate_data_reader,
        action_effect_timeout_seconds=_ACTION_EFFECT_TIMEOUT_SECONDS,
    )
    scheduler_reader = HASchedulerReader(hass, fallback_context["scheduler_ids"])
    timer_scheduler = Mock()
    timer_scheduler.schedule_timer = Mock(return_value=lambda: None)
    schedule_anticipation_action = ScheduleAnticipationActionUseCase(
        scheduler_reader=scheduler_reader,
        scheduler_commander=scheduler_commander,
        timer_scheduler=timer_scheduler,
        control_preheating_use_case=control_preheating,
    )
    orchestrator = HeatingOrchestrator(
        calculate_anticipation=_FakeCalculateAnticipation(fallback_context),
        control_preheating=control_preheating,
        schedule_anticipation_action=schedule_anticipation_action,
        update_cache=Mock(spec=UpdateCacheDataUseCase),
    )
    schedule_anticipation_action.set_on_scheduler_blocked(
        orchestrator.retry_anticipation_after_blocked_scheduler
    )
    fallback_context["control_preheating"] = control_preheating
    return orchestrator


@when(parsers.parse('IHP recalculates and schedules anticipation for "{entity_id}"'))
def recalculate_and_schedule(fallback_context: dict, entity_id: str) -> None:
    """WHEN: The orchestrator runs one full calculate+schedule cycle.

    "Now" (06:59) falls inside every configured slot's 5-minute anticipation
    window (target - 5min <= now < target), so ``schedule_action`` takes the
    immediate-trigger path for each candidate in turn and the orchestrator's
    retry loop runs synchronously within this one call.
    """
    orchestrator = _build_orchestrator(fallback_context)
    now = datetime.fromisoformat(f"{_TODAY}T06:59:00{_TZ}")

    async def _run() -> dict:
        with (
            patch.object(dt_util, "now", return_value=now.astimezone(UTC)),
            patch(
                f"{_CLIMATE_READER_MODULE}.async_track_state_change_event",
                side_effect=_make_state_change_tracker(fallback_context),
            ),
        ):
            return await orchestrator.calculate_and_schedule_anticipation(ihp_enabled=True)

    fallback_context["result"] = asyncio.run(_run())


@then(parsers.parse('the attempt on "{entity_id}" is confirmed blocked'))
def attempt_confirmed_blocked(fallback_context: dict, entity_id: str) -> None:
    """THEN: The blocked entity appears in this cycle's blocked_schedulers list."""
    assert entity_id in fallback_context["result"]["blocked_schedulers"]


@then(parsers.parse('IHP retries and succeeds with "{entity_id}" within the same cycle'))
def retries_and_succeeds(fallback_context: dict, entity_id: str) -> None:
    """THEN: The final anticipation data targets the fallback scheduler."""
    assert fallback_context["result"]["scheduler_entity"] == entity_id
    assert fallback_context["control_preheating"].is_preheating_active() is True
    assert fallback_context["control_preheating"].get_active_scheduler_entity() == entity_id


@then(parsers.parse('IHP is preheating for "{entity_id}"'))
def preheating_for(fallback_context: dict, entity_id: str) -> None:
    """THEN: The preheat is confirmed and tracked for this scheduler."""
    assert fallback_context["result"]["scheduler_entity"] == entity_id
    assert fallback_context["control_preheating"].is_preheating_active() is True
    assert fallback_context["control_preheating"].get_active_scheduler_entity() == entity_id


@then(parsers.parse('"{entity_id}" is never triggered'))
def never_triggered(fallback_context: dict, entity_id: str) -> None:
    """THEN: IHP sent no scheduler action for this entity."""
    triggered = [call["entity_id"] for call in fallback_context["service_calls"]]
    assert entity_id not in triggered


@then("no scheduler is reported blocked this cycle")
def no_scheduler_blocked(fallback_context: dict) -> None:
    """THEN: blocked_schedulers is empty."""
    assert fallback_context["result"]["blocked_schedulers"] == []


@then(parsers.parse("the room's target temperature becomes {temp:f}°C"))
def room_target_becomes(fallback_context: dict, temp: float) -> None:
    """THEN: The VTherm's target temperature reflects a successful trigger."""
    vtherm_state = fallback_context["states"][fallback_context["vtherm_id"]]
    assert vtherm_state.attributes["temperature"] == temp


@then(parsers.parse("the room's target temperature stays at {temp:f}°C"))
def room_target_stays(fallback_context: dict, temp: float) -> None:
    """THEN: No scheduler action was applied; the thermostat is untouched."""
    vtherm_state = fallback_context["states"][fallback_context["vtherm_id"]]
    assert vtherm_state.attributes["temperature"] == temp


@then("the anticipation data reports no scheduler blocked overall")
def reports_not_blocked_overall(fallback_context: dict) -> None:
    """THEN: scheduler_blocked is False - anticipation was delivered this cycle."""
    assert fallback_context["result"]["scheduler_blocked"] is False


@then("the anticipation data reports every scheduler blocked overall")
def reports_blocked_overall(fallback_context: dict) -> None:
    """THEN: scheduler_blocked is True - every candidate was exhausted."""
    assert fallback_context["result"]["scheduler_blocked"] is True


@then(parsers.parse('the blocked schedulers for this cycle are "{entity_ids}"'))
def blocked_schedulers_are(fallback_context: dict, entity_ids: str) -> None:
    """THEN: blocked_schedulers lists exactly the expected entities, in order."""
    expected = [e.strip() for e in entity_ids.split(",")]
    assert fallback_context["result"]["blocked_schedulers"] == expected
