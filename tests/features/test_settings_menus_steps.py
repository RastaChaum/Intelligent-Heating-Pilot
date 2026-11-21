"""pytest-bdd steps for the options menu of a device: the flow over a simulated entry (#302)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_CLIMATE_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    DOMAIN,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.entry_changes import (
    effective_values,
)

scenarios("settings_menus.feature")

LIVING = "climate.living"


class Device:
    """A device entry whose writes are applied like the config entries registry does."""

    def __init__(self) -> None:
        self.entry = Mock(entry_id="device", title="Living room", unique_id=LIVING)
        self.entry.data = {CONF_CLIMATE_ENTITY: LIVING}
        self.entry.options = {CONF_LHS_RETENTION_DAYS: 30}
        self.entry.state = Mock()
        self.others: list[Mock] = []
        self.reloads: list[str] = []
        self.hass = Mock()
        self.hass.states.get.return_value = None
        self.hass.states.async_all.return_value = []
        self.hass.config.language = "en"
        self.hass.config_entries.async_entries.side_effect = lambda _d: [self.entry, *self.others]
        self.hass.config_entries.async_update_entry.side_effect = self._update
        self.hass.config_entries.async_schedule_reload.side_effect = self.reloads.append
        self._run_device()

    def _run_device(self) -> None:
        """The device runs with what is stored now."""
        from homeassistant.config_entries import ConfigEntryState

        self.entry.state = ConfigEntryState.LOADED
        coordinator = Mock(_options_snapshot=effective_values(self.entry))
        self.hass.data = {DOMAIN: {"device": coordinator}}

    def _update(self, entry: Mock, **changes: Any) -> None:
        for name, value in changes.items():
            setattr(entry, name, value)

    def new_flow(self) -> IntelligentHeatingPilotOptionsFlow:
        flow = IntelligentHeatingPilotOptionsFlow()
        flow.hass = self.hass
        flow.async_show_menu = Mock(side_effect=lambda **kw: {"type": "menu", **kw})
        flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
        flow.async_create_entry = Mock(side_effect=lambda **kw: {"type": "create_entry", **kw})
        return flow


@pytest.fixture
def context() -> dict:
    device = Device()
    patcher = patch.object(
        IntelligentHeatingPilotOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=device.entry,
    )
    translations = [
        patch(
            f"custom_components.intelligent_heating_pilot.{module}.async_get_translations",
            AsyncMock(return_value={}),
        )
        for module in ("config_flow_themes", "config_flow_overrides")
    ]
    patcher.start()
    for translation in translations:
        translation.start()
    yield {"device": device, "flow": device.new_flow(), "result": None}
    for translation in translations:
        translation.stop()
    patcher.stop()


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _open(context: dict) -> None:
    context["flow"] = context["device"].new_flow()
    context["result"] = _run(context["flow"].async_step_init())


def _choose(context: dict, step: str) -> None:
    context["result"] = _run(getattr(context["flow"], f"async_step_{step}")())


@given(parsers.parse("an IHP device with a data retention of {days:d} days"))
def a_device(context: dict, days: int) -> None:
    context["device"].entry.options = {CONF_LHS_RETENTION_DAYS: days}
    context["device"]._run_device()


@given(parsers.parse('another IHP device drives "{vtherm}"'))
def another_device(context: dict, vtherm: str) -> None:
    other = Mock(entry_id="other", options={})
    other.data = {CONF_CLIMATE_ENTITY: vtherm}
    context["device"].others.append(other)


@given(parsers.parse('I saved a data retention of {days:d} days in the "{theme}" theme'))
def saved_in_theme(context: dict, days: int, theme: str) -> None:
    _open(context)
    _choose(context, theme)
    _override_retention(context, theme, days)


@when("I open the device options")
def open_options(context: dict) -> None:
    _open(context)


@when(parsers.parse('I open the device options and choose the "{theme}" theme'))
def open_and_choose(context: dict, theme: str) -> None:
    _open(context)
    _choose(context, theme)


def _override_retention(context: dict, theme: str, days: int) -> None:
    """Override the retention in its theme: pick it, then give its value."""
    flow = context["flow"]
    _run(getattr(flow, f"async_step_{theme}")({"overridden_settings": [CONF_LHS_RETENTION_DAYS]}))
    context["result"] = _run(
        getattr(flow, f"async_step_{theme}_values")({CONF_LHS_RETENTION_DAYS: days})
    )


@when(parsers.parse("I set the data retention to {days:d} days and save"))
def set_retention(context: dict, days: int) -> None:
    _override_retention(context, "learning", days)


@when(parsers.parse('I submit the thermostat "{vtherm}"'))
def submit_thermostat(context: dict, vtherm: str) -> None:
    context["result"] = _run(
        context["flow"].async_step_thermostat_schedulers({CONF_CLIMATE_ENTITY: vtherm})
    )


@when("I close the dialog and open the device options again")
def close_and_reopen(context: dict) -> None:
    _open(context)


@when(parsers.parse('I choose "{entry}"'))
def choose_entry(context: dict, entry: str) -> None:
    _choose(context, entry.lower())


@then("the options menu is shown again")
def menu_is_shown(context: dict) -> None:
    assert context["result"]["type"] == "menu" and context["result"]["step_id"] == "init"


@then(parsers.parse("the data retention stored for the device is {days:d} days"))
def stored_retention(context: dict, days: int) -> None:
    assert context["device"].entry.options[CONF_LHS_RETENTION_DAYS] == days


@then("the device has not reloaded")
def not_reloaded(context: dict) -> None:
    assert context["device"].reloads == []


@then("the device has reloaded once")
def reloaded_once(context: dict) -> None:
    assert context["device"].reloads == ["device"]


@then(parsers.parse('the menu offers "{entry}"'))
def menu_offers(context: dict, entry: str) -> None:
    assert entry.lower() in _menu_options(context)


@then(parsers.parse('the menu does not offer "{entry}"'))
def menu_does_not_offer(context: dict, entry: str) -> None:
    assert entry.lower() not in _menu_options(context)


def _menu_options(context: dict) -> list[str]:
    result = context["result"]
    assert result["type"] == "menu"
    return result["menu_options"]


@then("the wake-up sources menu is shown")
def wake_up_menu(context: dict) -> None:
    assert context["result"]["type"] == "menu"
    assert context["result"]["step_id"] == "wake_up_menu"


@then(parsers.parse('the form stays open with the error "{error}"'))
def form_error(context: dict, error: str) -> None:
    assert context["result"]["type"] == "form"
    assert error in context["result"]["errors"].values()


@then(parsers.parse('the thermostat stored for the device is "{vtherm}"'))
def stored_thermostat(context: dict, vtherm: str) -> None:
    entry = context["device"].entry
    assert entry.options.get(CONF_CLIMATE_ENTITY, entry.data[CONF_CLIMATE_ENTITY]) == vtherm
