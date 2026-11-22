"""One driver per scheduler integration, behind the same small interface.

A driver turns a list of ``Block`` into the real scheduler's own configuration (a native
``schedule`` helper, a HACS Scheduler switch, a Climate Scheduler group), so a scenario is
written once and runs against every scheduler IHP supports.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol
from unittest.mock import patch

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import CONF_NATIVE_SCHEDULE_DRIVE
from tests.integration.real_components.home import (
    BOOST_C,
    COMFORT_C,
    ECO_C,
    THERMOSTAT,
    Block,
    Home,
)

SCHEDULE_NAME = "Heating"
NATIVE_ENTITY = "schedule.heating"
SWITCH_ENTITY = "switch.schedule_heating"
DEFAULT_BLOCK_HOURS = 2
END_OF_DAY = "23:59:59"
CLIMATE_SCHEDULER_SETTLE = timedelta(seconds=6)
PRESET_TEMPERATURES = {"eco": ECO_C, "comfort": COMFORT_C, "boost": BOOST_C}
NIGHT_NODE = {"time": "22:00", "temp": ECO_C, "preset_mode": "eco"}


class SchedulerDriver(Protocol):
    """What a scenario needs from a scheduler."""

    name: str
    entity_id: str
    ihp_options: dict[str, Any]

    async def install(self, home: Home, blocks: list[Block]) -> str:
        """Create the scheduler with these Monday blocks and return its entity id."""

    async def replace(self, home: Home, blocks: list[Block]) -> None:
        """Change the blocks of the installed scheduler (none removes them all)."""


def _end_of(blocks: list[Block], index: int) -> str:
    """A block lasts until the next one starts, or a couple of hours when it is the last."""
    if index + 1 < len(blocks):
        return f"{blocks[index + 1].time}:00"
    hour, minute = (int(part) for part in blocks[index].time.split(":"))
    end_hour = hour + DEFAULT_BLOCK_HOURS
    return f"{end_hour:02d}:{minute:02d}:00" if end_hour < 24 else END_OF_DAY


class NativeSchedule:
    """Home Assistant's own ``schedule`` helper, driven by IHP on opt-in."""

    name = "native"
    entity_id = NATIVE_ENTITY

    def __init__(self, **ihp_options: Any) -> None:
        self.ihp_options: dict[str, Any] = {CONF_NATIVE_SCHEDULE_DRIVE: True, **ihp_options}

    def _config(self, blocks: list[Block]) -> dict[str, Any]:
        monday = []
        for index, block in enumerate(blocks):
            item: dict[str, Any] = {"from": f"{block.time}:00", "to": _end_of(blocks, index)}
            data = _native_data(block)
            if data:
                item["data"] = data
            monday.append(item)
        return {"schedule": {"heating": {"name": SCHEDULE_NAME, "monday": monday}}}

    async def install(self, home: Home, blocks: list[Block]) -> str:
        assert await async_setup_component(home.hass, "schedule", self._config(blocks))
        await home.hass.async_block_till_done()
        return self.entity_id

    async def replace(self, home: Home, blocks: list[Block]) -> None:
        with patch("homeassistant.config.load_yaml_config_file", return_value=self._config(blocks)):
            await home.hass.services.async_call("schedule", "reload", blocking=True)
        await home.hass.async_block_till_done()


def _native_data(block: Block) -> dict[str, Any]:
    if block.data is not None:
        return dict(block.data)
    data: dict[str, Any] = {}
    if block.preset is not None:
        data["preset"] = block.preset
    if block.temperature is not None:
        data["temperature"] = block.temperature
    return data


class HacsScheduler:
    """HACS Scheduler (nielsfaber), whose own ``run_action`` IHP calls."""

    name = "hacs"
    entity_id = SWITCH_ENTITY

    def __init__(self) -> None:
        self.ihp_options: dict[str, Any] = {}

    def timeslots(self, blocks: list[Block], **extra: Any) -> list[dict[str, Any]]:
        return [
            {
                "start": f"{block.time}:00",
                "stop": _end_of(blocks, index),
                "actions": [_hacs_action(block)],
                **extra,
            }
            for index, block in enumerate(blocks)
        ]

    async def install(self, home: Home, blocks: list[Block], **extra: Any) -> str:
        entry = MockConfigEntry(domain="scheduler", title="Scheduler", data={})
        entry.add_to_hass(home.hass)
        assert await home.hass.config_entries.async_setup(entry.entry_id)
        await home.hass.services.async_call(
            "scheduler",
            "add",
            {
                "weekdays": ["mon"],
                "repeat_type": "repeat",
                "name": SCHEDULE_NAME,
                "timeslots": self.timeslots(blocks, **extra),
            },
            blocking=True,
        )
        await home.hass.async_block_till_done()
        return self.entity_id

    async def replace(self, home: Home, blocks: list[Block]) -> None:
        await home.hass.services.async_call(
            "scheduler",
            "edit",
            {"entity_id": self.entity_id, "timeslots": self.timeslots(blocks)},
            blocking=True,
        )
        await home.hass.async_block_till_done()


def _hacs_action(block: Block) -> dict[str, Any]:
    if block.preset is not None:
        return {
            "service": "climate.set_preset_mode",
            "entity_id": THERMOSTAT,
            "service_data": {"preset_mode": block.preset},
        }
    return {
        "service": "climate.set_temperature",
        "entity_id": THERMOSTAT,
        "service_data": {"temperature": block.temperature},
    }


class ClimateScheduler:
    """Climate Scheduler (kneave): a group of climates with timed nodes, one switch for it."""

    name = "climate_scheduler"
    entity_id = SWITCH_ENTITY

    def __init__(self) -> None:
        self.ihp_options: dict[str, Any] = {}

    def nodes(self, blocks: list[Block]) -> list[dict[str, Any]]:
        # Climate Scheduler applies the node in force as soon as it knows the group, so the room
        # rests in the night node until the morning one is anticipated.
        return [NIGHT_NODE, *(_node(block) for block in blocks)]

    async def _call(self, home: Home, service: str, data: dict[str, Any]) -> None:
        await home.hass.services.async_call("climate_scheduler", service, data, blocking=True)

    async def install(self, home: Home, blocks: list[Block]) -> str:
        entry = MockConfigEntry(domain="climate_scheduler", title="Climate Scheduler", data={})
        entry.add_to_hass(home.hass)
        assert await home.hass.config_entries.async_setup(entry.entry_id)
        await self._call(home, "create_group", {"schedule_id": SCHEDULE_NAME})
        await self._call(
            home, "add_to_group", {"schedule_id": SCHEDULE_NAME, "entity_id": THERMOSTAT}
        )
        await self.replace(home, blocks)
        return self.entity_id

    async def replace(self, home: Home, blocks: list[Block]) -> None:
        await self._call(
            home, "set_group_schedule", {"schedule_id": SCHEDULE_NAME, "nodes": self.nodes(blocks)}
        )
        # The component sleeps while it starts its entities
        await home.advance(CLIMATE_SCHEDULER_SETTLE)


def _node(block: Block) -> dict[str, Any]:
    if block.preset is not None:
        return {
            "time": block.time,
            "temp": PRESET_TEMPERATURES[block.preset],
            "preset_mode": block.preset,
        }
    return {"time": block.time, "temp": block.temperature}


ALL_SCHEDULERS = (NativeSchedule, HacsScheduler, ClimateScheduler)
