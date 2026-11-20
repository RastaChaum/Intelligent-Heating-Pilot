"""pytest-bdd steps for the central configuration and the override of a device value (#302)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.const import (
    CONF_ENTRY_TYPE,
    CONF_LHS_RETENTION_DAYS,
    CONF_NAME,
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_SCHEDULER_ENTITIES,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_VTHERM_ENTITY,
    DEFAULT_LHS_RETENTION_DAYS,
    ENTRY_TYPE_CENTRAL,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.central_entry import (
    apply_central_changes,
    central_values_of,
    set_applied_central_values,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)

scenarios("central_configuration.feature", "inherit_override_reset.feature")

SENSORS = {"outdoor temperature sensor": CONF_TEMPERATURE_OUT_ENTITY}


class Installation:
    """Devices and a central configuration, as config entries would hold them."""

    def __init__(self) -> None:
        self.central: dict[str, Any] | None = {}
        self.devices: list[Mock] = []
        self.reloaded: list[str] = []
        self.hass = Mock()
        self.hass.data = {}
        self.hass.async_create_task = lambda coro: asyncio.new_event_loop().run_until_complete(coro)

        async def reload(entry_id: str) -> None:
            self.reloaded.append(entry_id)

        self.hass.config_entries.async_reload = reload
        self.hass.config_entries.async_entries.side_effect = lambda _d: self._entries()

    def _central_entry(self) -> Mock | None:
        if self.central is None:
            return None
        entry = Mock(
            entry_id="central", title="Central", data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
        )
        entry.options = self.central
        return entry

    def _entries(self) -> list[Mock]:
        central = self._central_entry()
        return [*self.devices, *([central] if central else [])]

    def add_device(
        self, options: Mapping[str, Any] | None = None, data: Mapping | None = None
    ) -> Mock:
        n = len(self.devices)
        device = Mock(entry_id=f"device_{n}", title=f"Device {n}")
        device.data = {
            CONF_NAME: f"Device {n}",
            CONF_VTHERM_ENTITY: f"climate.d{n}",
            **(data or {}),
        }
        device.options = dict(options or {})
        self.devices.append(device)
        return device

    def read(self, device: Mock) -> Any:
        reader = HADeviceConfigReader(self.hass, device)
        return asyncio.new_event_loop().run_until_complete(
            reader.get_device_config(device.entry_id)
        )


@pytest.fixture
def world() -> Installation:
    return Installation()


def _ordinal(world: Installation, which: str) -> Mock:
    return world.devices[{"first": 0, "second": 1}[which]]


@given("two IHP devices that override no setting")
def two_devices(world: Installation) -> None:
    world.add_device()
    world.add_device()


@given("an IHP device that overrides nothing")
def one_device(world: Installation) -> None:
    world.add_device()


@given(parsers.parse("an IHP device that overrides its data retention with {days:d} days"))
def device_with_retention(world: Installation, days: int) -> None:
    world.add_device({CONF_LHS_RETENTION_DAYS: days})


@given(parsers.parse("the {which} device overrides the data retention with {days:d} days"))
def nth_overrides(world: Installation, which: str, days: int) -> None:
    _ordinal(world, which).options[CONF_LHS_RETENTION_DAYS] = days


@given(
    parsers.parse(
        "a device created before the central configuration with a data retention of {days:d} days"
    )
)
def legacy_device(world: Installation, days: int) -> None:
    world.add_device(data={CONF_LHS_RETENTION_DAYS: days})


@given(parsers.parse("a central data retention of {days:d} days"))
def central_retention(world: Installation, days: int) -> None:
    world.central = {CONF_LHS_RETENTION_DAYS: days}
    set_applied_central_values(world.hass, world.central)


@given(parsers.parse('a central {sensor} "{entity}"'))
def central_sensor(world: Installation, sensor: str, entity: str) -> None:
    world.central = {SENSORS[sensor]: entity}
    set_applied_central_values(world.hass, world.central)


@given(parsers.parse("a central configuration holding a native schedule drive of true"))
def central_drive(world: Installation) -> None:
    world.central = {CONF_NATIVE_SCHEDULE_DRIVE: True}


@given("no central configuration")
def no_central(world: Installation) -> None:
    world.central = None


@when(parsers.parse('I change the central {sensor} to "{entity}"'))
def change_central_sensor(world: Installation, sensor: str, entity: str) -> None:
    assert world.central is not None
    world.central[SENSORS[sensor]] = entity


@when(parsers.parse("I change the central data retention to {days:d} days"))
def change_central_retention(world: Installation, days: int) -> None:
    assert world.central is not None
    world.central[CONF_LHS_RETENTION_DAYS] = days


@when(parsers.parse("I change the central data retention to {days:d} days and apply"))
def change_and_apply(world: Installation, days: int) -> None:
    change_central_retention(world, days)
    central = world._central_entry()
    assert central is not None
    apply_central_changes(world.hass, central)


@when(parsers.parse('I set the data retention of the device back to "inherit" and apply'))
def reset_to_inherit(world: Installation) -> None:
    world.devices[0].options.pop(CONF_LHS_RETENTION_DAYS, None)
    world.devices[0].data.pop(CONF_LHS_RETENTION_DAYS, None)


@when(parsers.parse("I override the data retention of the device with {days:d} days"))
def override_retention(world: Installation, days: int) -> None:
    world.devices[0].options[CONF_LHS_RETENTION_DAYS] = days


@when(parsers.parse("I override the {sensor} of the device with none"))
def override_none(world: Installation, sensor: str) -> None:
    world.devices[0].options[SENSORS[sensor]] = None


@when("a device is created with a name, a thermostat and schedulers")
def create_device(world: Installation) -> None:
    world.created = {  # type: ignore[attr-defined]
        CONF_NAME: "Room",
        CONF_VTHERM_ENTITY: "climate.room",
        CONF_SCHEDULER_ENTITIES: ["switch.plan"],
    }


@then(parsers.parse('both devices use "{entity}"'))
def both_use(world: Installation, entity: str) -> None:
    assert [world.read(d).temperature_out_entity_id for d in world.devices] == [entity, entity]


@then(parsers.parse("the {which} device uses a data retention of {days:d} days"))
def nth_retention(world: Installation, which: str, days: int) -> None:
    assert world.read(_ordinal(world, which)).lhs_retention_days == days


@then(parsers.parse("the device uses a data retention of {days:d} days"))
def device_retention(world: Installation, days: int) -> None:
    assert world.read(world.devices[0]).lhs_retention_days == days


@then(parsers.parse("that device uses a data retention of {days:d} days"))
def that_device_retention(world: Installation, days: int) -> None:
    assert world.read(world.devices[0]).lhs_retention_days == days


@then(parsers.parse("both devices use the built-in data retention of {days:d} days"))
def builtin_retention(world: Installation, days: int) -> None:
    assert days == DEFAULT_LHS_RETENTION_DAYS
    assert [world.read(d).lhs_retention_days for d in world.devices] == [days, days]


@then("only the first device is reloaded")
def only_first_reloaded(world: Installation) -> None:
    assert world.reloaded == ["device_0"]


@then("the device uses no outdoor temperature sensor")
def no_sensor(world: Installation) -> None:
    assert world.read(world.devices[0]).temperature_out_entity_id is None


@then("the device does not drive native schedules")
def no_drive(world: Installation) -> None:
    assert world.read(world.devices[0]).native_schedule_drive is False


@then("the device stores only those three values")
def stores_three(world: Installation) -> None:
    assert set(world.created) == {CONF_NAME, CONF_VTHERM_ENTITY, CONF_SCHEDULER_ENTITIES}  # type: ignore[attr-defined]
    assert not set(world.created) & set(central_values_of(Mock(options=world.created)))  # type: ignore[attr-defined]
