"""A release candidate in a real Home Assistant: it loads, preheats on every scheduler, restarts.

One container holds three rooms, each with a real Versatile Thermostat, IHP and one scheduler
(native schedule, HACS Scheduler, Climate Scheduler). Their slot is a few minutes away on the real
clock; IHP must put the thermostat in the slot's preset before the slot starts.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.e2e.stack import TIMEZONE, HomeAssistantStack, Room, StackError

SLOT_DELAY = timedelta(minutes=10)
ROOM_C = 20.7  # 0.3°C below comfort: IHP heads for the slot about 9 minutes ahead
OUTDOOR_C = 5.0
ECO_C, COMFORT_C, BOOST_C = 17.0, 21.0, 23.0
PRESET_WAIT_SECONDS = 15 * 60
ENTRY_WAIT_SECONDS = 120
IHP_DOMAIN = "intelligent_heating_pilot"
SENSOR_ANTICIPATED = "anticipated_start_time"
# An empty history is normal on a first start: IHP says so at ERROR level
EXPECTED_ERRORS = ("missing REQUIRED data keys", "Missing critical historical data keys")
OUR_LOGGERS = (
    "custom_components.intelligent_heating_pilot",
    "custom_components.versatile_thermostat",
    "custom_components.scheduler",
    "custom_components.climate_scheduler",
)

NATIVE = Room("native")
HACS = Room("hacs")
CLIMATE_SCHEDULER = Room("cs")
ROOMS = [NATIVE, HACS, CLIMATE_SCHEDULER]
SCHEDULE_ENTITIES = {
    NATIVE.key: "schedule.native",
    HACS.key: "switch.schedule_hacs",
    CLIMATE_SCHEDULER.key: "switch.schedule_cs",
}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass
class Scenario:
    stack: HomeAssistantStack
    slot: datetime
    ihp_entries: dict[str, str]


def _entry_dict(domain: str, title: str, entry_id: str, data: dict, options: dict | None = None):
    return MockConfigEntry(
        domain=domain, title=title, entry_id=entry_id, data=data, options=options or {}
    ).as_dict()


def _seeded_entries() -> list[dict]:
    from custom_components.intelligent_heating_pilot.const import (
        CONF_NATIVE_SCHEDULE_DRIVE,
        CONF_SCHEDULER_ENTITIES,
        CONF_VTHERM_ENTITY,
    )
    from tests.integration.real_components.home import vtherm_entry_data

    entries = [
        _entry_dict("scheduler", "Scheduler", "0000000000000000000000scheduler", {}),
        _entry_dict("climate_scheduler", "Climate Scheduler", "0000000000climatescheduler00", {}),
    ]
    outdoor = "input_number.outdoor_temperature"
    for room in ROOMS:
        entries.append(
            _entry_dict(
                "versatile_thermostat",
                room.name,
                f"vtherm{room.key:0>22}",
                vtherm_entry_data(room.name, room.sensor, outdoor, room.heater),
            )
        )
        options = {CONF_NATIVE_SCHEDULE_DRIVE: True} if room is NATIVE else {}
        entries.append(
            _entry_dict(
                IHP_DOMAIN,
                f"IHP {room.name}",
                f"ihp{room.key:0>25}",
                {
                    CONF_VTHERM_ENTITY: room.thermostat,
                    CONF_SCHEDULER_ENTITIES: [SCHEDULE_ENTITIES[room.key]],
                },
                options,
            )
        )
    return entries


def _entry_ids() -> dict[str, str]:
    return {room.key: f"ihp{room.key:0>25}" for room in ROOMS}


@pytest.fixture(scope="module")
def stack(
    workdir: Path, components_root: Path, ha_image: str, container_logs: Path
) -> Iterator[HomeAssistantStack]:
    from tests.e2e.stack import REPO_COMPONENT

    ha = HomeAssistantStack(workdir, ha_image)
    ha.stop()
    integrations = {
        domain: components_root / domain
        for domain in ("versatile_thermostat", "scheduler", "climate_scheduler")
    }
    integrations[IHP_DOMAIN] = REPO_COMPONENT
    ha.prepare(ROOMS, _seeded_entries(), integrations)
    try:
        ha.start()
        ha.onboard()
        yield ha
    finally:
        container_logs.write_text(ha.logs())
        ha.stop()


def _service(stack: HomeAssistantStack, domain: str, service: str, **data: object) -> None:
    stack.call(domain, service, data)


def _offers_presets(stack: HomeAssistantStack, room: Room) -> bool:
    state = stack.state(room.thermostat)
    return state is not None and bool(state["attributes"].get("preset_modes"))


def _prepare_rooms(stack: HomeAssistantStack) -> None:
    """The rooms are a little cold and rest in eco, with the presets the user has set."""
    stack.wait_for(
        lambda: all(_offers_presets(stack, room) for room in ROOMS),
        ENTRY_WAIT_SECONDS,
        "the thermostats to be ready",
    )
    _service(stack, "input_number", "set_value", entity_id="input_number.outdoor_temperature",
             value=OUTDOOR_C)  # fmt: skip
    for room in ROOMS:
        _service(stack, "input_number", "set_value", entity_id=room.sensor, value=ROOM_C)
        _service(stack, "climate", "set_hvac_mode", entity_id=room.thermostat, hvac_mode="heat")
        for preset, celsius in (("eco", ECO_C), ("comfort", COMFORT_C), ("boost", BOOST_C)):
            _service(stack, "number", "set_value", value=celsius,
                     entity_id=f"number.{room.key}_room_preset_{preset}_temp")  # fmt: skip
        # Versatile Thermostat publishes a preset's temperature once the preset was selected
        for preset in ("boost", "comfort", "eco"):
            _service(stack, "climate", "set_preset_mode", entity_id=room.thermostat,
                     preset_mode=preset)  # fmt: skip


def _create_schedulers(stack: HomeAssistantStack, slot: datetime) -> None:
    start = slot.strftime("%H:%M:%S")
    end = slot + timedelta(hours=1)
    # A block cannot cross midnight: the test may run late in the evening
    stop = end.strftime("%H:%M:%S") if end.date() == slot.date() else "23:59:59"
    stack.websocket(
        {
            "type": "schedule/create",
            "name": "Native",
            **{
                day: [{"from": start, "to": stop, "data": {"preset": "comfort"}}]
                for day in WEEKDAYS
            },
        }
    )
    _service(
        stack, "scheduler", "add",
        weekdays=["daily"], repeat_type="repeat", name="Hacs",
        timeslots=[{"start": start, "stop": stop, "actions": [{
            "service": "climate.set_preset_mode", "entity_id": HACS.thermostat,
            "service_data": {"preset_mode": "comfort"}}]}],
    )  # fmt: skip
    night = (slot - timedelta(hours=2)).strftime("%H:%M")
    _service(stack, "climate_scheduler", "create_group", schedule_id="Cs")
    _service(stack, "climate_scheduler", "add_to_group", schedule_id="Cs",
             entity_id=CLIMATE_SCHEDULER.thermostat)  # fmt: skip
    _service(
        stack, "climate_scheduler", "set_group_schedule", schedule_id="Cs",
        nodes=[
            {"time": night, "temp": ECO_C, "preset_mode": "eco"},
            {"time": slot.strftime("%H:%M"), "temp": COMFORT_C, "preset_mode": "comfort"},
        ],
    )  # fmt: skip


def _make_climate_scheduler_expose_its_switch(stack: HomeAssistantStack) -> None:
    """Climate Scheduler creates the switch of a group when it loads, not when it is created."""
    _service(stack, "climate_scheduler", "reload_integration")


def _reload_ihp(stack: HomeAssistantStack) -> None:
    for entry_id in _entry_ids().values():
        _service(stack, "homeassistant", "reload_config_entry", entry_id=entry_id)


@pytest.fixture(scope="module")
def scenario(stack: HomeAssistantStack) -> Scenario:
    _prepare_rooms(stack)
    now = datetime.now(ZoneInfo(TIMEZONE))
    slot = (now + SLOT_DELAY).replace(second=0, microsecond=0) + timedelta(minutes=1)
    _create_schedulers(stack, slot)
    _make_climate_scheduler_expose_its_switch(stack)
    stack.wait_for(
        lambda: all(stack.state(entity) is not None for entity in SCHEDULE_ENTITIES.values()),
        ENTRY_WAIT_SECONDS,
        "the schedulers",
    )
    _reload_ihp(stack)
    return Scenario(stack, slot, _entry_ids())


def _loaded(stack: HomeAssistantStack) -> dict[str, str]:
    return {entry["entry_id"]: entry["state"] for entry in stack.config_entries()}


def test_every_integration_is_loaded(scenario: Scenario) -> None:
    states = _loaded(scenario.stack)
    assert states, "Home Assistant reports no config entry"
    assert {s for s in states.values()} == {"loaded"}, states


@pytest.mark.parametrize("room", ROOMS, ids=lambda room: room.key)
def test_ihp_publishes_its_entities(scenario: Scenario, room: Room) -> None:
    registry = scenario.stack.websocket({"type": "config/entity_registry/list"})
    entry_id = scenario.ihp_entries[room.key]
    entities = [e["entity_id"] for e in registry if e.get("config_entry_id") == entry_id]
    # The second and third IHP of a home get a numeric suffix on every entity id
    assert any(re.search(rf"{SENSOR_ANTICIPATED}(_\d+)?$", entity) for entity in entities), entities


@pytest.mark.parametrize("room", ROOMS, ids=lambda room: room.key)
def test_the_slot_preset_is_applied_before_the_slot(scenario: Scenario, room: Room) -> None:
    stack = scenario.stack

    def comfort() -> bool:
        state = stack.state(room.thermostat)
        return state is not None and state["attributes"].get("preset_mode") == "comfort"

    seconds = max((scenario.slot - datetime.now(scenario.slot.tzinfo)).total_seconds(), 0)
    stack.wait_for(comfort, min(seconds + 60, PRESET_WAIT_SECONDS), f"{room.thermostat} comfort")
    changed = datetime.fromisoformat(stack.state(room.thermostat)["last_changed"])
    assert changed < scenario.slot, f"applied at {changed}, after the slot {scenario.slot}"


def _errors(logs: str) -> list[str]:
    found = []
    for line in logs.splitlines():
        if " ERROR " not in line or not any(name in line for name in OUR_LOGGERS):
            continue
        if not any(expected in line for expected in EXPECTED_ERRORS):
            found.append(re.sub(r"\x1b\[[0-9;]*m", "", line))
    return found


def test_the_logs_hold_no_unexpected_error(scenario: Scenario) -> None:
    assert _errors(scenario.stack.logs()) == []


def test_everything_comes_back_after_a_restart(scenario: Scenario) -> None:
    stack = scenario.stack
    stack.restart()
    stack.wait_for(
        lambda: _all_loaded(stack), ENTRY_WAIT_SECONDS, "every config entry loaded again"
    )
    assert _errors(stack.logs()) == []


def _all_loaded(stack: HomeAssistantStack) -> bool:
    try:
        states = _loaded(stack)
    except (StackError, OSError):
        return False
    return bool(states) and set(states.values()) == {"loaded"}
