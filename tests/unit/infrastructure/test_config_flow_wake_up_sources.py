"""Tests for the wake-up sources part of the options flow: menu, validation, saved options."""

from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_MANAGE_WAKE_UP_SOURCES,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    CONF_WAKE_UP_SOURCES,
)

ALARM = "sensor.phone_next_alarm"
ARRIVAL = "input_datetime.arrival"
VTHERM = "climate.vtherm"


def _entry(options: dict | None = None, schedulers: list[str] | None = None) -> Mock:
    entry = Mock()
    entry.entry_id = "device"
    entry.title = "Living room"
    entry.unique_id = VTHERM
    entry.data = {CONF_VTHERM_ENTITY: VTHERM, CONF_SCHEDULER_ENTITIES: schedulers or []}
    entry.options = options or {}
    return entry


@pytest.fixture
def flow():
    """An options flow over a mocked entry, collecting what it shows and saves."""
    hass = Mock()
    hass.states.get.return_value = None
    hass.states.async_all.return_value = []
    hass.config_entries.async_entries.return_value = []
    entry = _entry()
    instance = IntelligentHeatingPilotOptionsFlow()
    instance.hass = hass
    instance.async_show_menu = Mock(side_effect=lambda **kw: {"type": "menu", **kw})
    instance.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
    instance.async_create_entry = Mock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    with patch.object(
        IntelligentHeatingPilotOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=entry,
    ):
        instance.entry = entry  # type: ignore[attr-defined]
        yield instance


def _main_form(**extra) -> dict:
    return {CONF_VTHERM_ENTITY: VTHERM, **extra}


@pytest.mark.asyncio
async def test_without_the_flag_the_options_are_saved_as_before(flow) -> None:
    result = await flow.async_step_init(_main_form())

    assert result["type"] == "create_entry"
    assert CONF_MANAGE_WAKE_UP_SOURCES not in result["data"]
    assert CONF_WAKE_UP_SOURCES not in result["data"]


@pytest.mark.asyncio
async def test_the_flag_opens_the_menu_and_is_never_stored(flow) -> None:
    result = await flow.async_step_init(_main_form(manage_wake_up_sources=True))

    assert result["type"] == "menu" and result["step_id"] == "wake_up_menu"
    assert result["menu_options"] == ["wake_up_add", "wake_up_done"]
    done = await flow.async_step_wake_up_done()
    assert CONF_MANAGE_WAKE_UP_SOURCES not in done["data"]


@pytest.mark.asyncio
async def test_a_source_is_added_and_saved_with_the_options(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    form = await flow.async_step_wake_up_add()
    assert form["step_id"] == "wake_up_form"

    menu = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    assert menu["step_id"] == "wake_up_menu"
    assert "wake_up_edit" in menu["menu_options"] and "wake_up_remove" in menu["menu_options"]

    done = await flow.async_step_wake_up_done()
    (stored,) = done["data"][CONF_WAKE_UP_SOURCES]
    assert stored["entity_id"] == ALARM and stored["target_preset"] == "comfort"


@pytest.mark.asyncio
async def test_empty_optional_fields_are_not_stored(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    await flow.async_step_wake_up_form(
        {"entity_id": ALARM, "target_preset": "", "target_temperature": 21, "hold_minutes": 0}
    )
    done = await flow.async_step_wake_up_done()

    (stored,) = done["data"][CONF_WAKE_UP_SOURCES]
    assert "target_preset" not in stored
    assert stored["target_temperature"] == 21


@pytest.mark.asyncio
async def test_a_source_without_any_target_is_refused(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))

    result = await flow.async_step_wake_up_form({"entity_id": ALARM})

    assert result["step_id"] == "wake_up_form"
    assert result["errors"] == {"base": "wake_up_target_required"}


@pytest.mark.asyncio
async def test_from_schedule_without_a_scheduler_needs_a_fixed_target(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_from_schedule": True})

    assert result["errors"] == {"base": "wake_up_target_required"}


@pytest.mark.asyncio
async def test_from_schedule_with_a_scheduler_is_accepted(flow) -> None:
    await flow.async_step_init(
        _main_form(manage_wake_up_sources=True, scheduler_entities=["switch.plan"])
    )

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_from_schedule": True})

    assert result["step_id"] == "wake_up_menu"


@pytest.mark.asyncio
async def test_the_from_schedule_field_is_only_offered_with_a_scheduler(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    without = await flow.async_step_wake_up_add()
    await flow.async_step_init(
        _main_form(manage_wake_up_sources=True, scheduler_entities=["switch.plan"])
    )
    with_scheduler = await flow.async_step_wake_up_add()

    assert "target_from_schedule" not in {str(k) for k in without["data_schema"].schema}
    assert "target_from_schedule" in {str(k) for k in with_scheduler["data_schema"].schema}


@pytest.mark.asyncio
async def test_an_entity_can_only_be_a_source_once(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "eco"})

    assert result["errors"] == {"base": "wake_up_duplicate"}


@pytest.mark.asyncio
async def test_a_source_is_edited_in_place(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    await flow.async_step_wake_up_form({"entity_id": ARRIVAL, "target_temperature": 20})

    picker = await flow.async_step_wake_up_edit()
    assert picker["step_id"] == "wake_up_edit"
    form = await flow.async_step_wake_up_edit({"entity_id": ALARM})
    assert form["step_id"] == "wake_up_form"
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "boost"})

    done = await flow.async_step_wake_up_done()
    by_entity = {s["entity_id"]: s for s in done["data"][CONF_WAKE_UP_SOURCES]}
    assert by_entity[ALARM]["target_preset"] == "boost"
    assert ARRIVAL in by_entity and len(by_entity) == 2


@pytest.mark.asyncio
async def test_sources_are_removed(flow) -> None:
    await flow.async_step_init(_main_form(manage_wake_up_sources=True))
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    await flow.async_step_wake_up_form({"entity_id": ARRIVAL, "target_temperature": 20})

    menu = await flow.async_step_wake_up_remove({"entity_id": [ALARM]})
    assert menu["step_id"] == "wake_up_menu"
    done = await flow.async_step_wake_up_done()

    assert [s["entity_id"] for s in done["data"][CONF_WAKE_UP_SOURCES]] == [ARRIVAL]


@pytest.mark.asyncio
async def test_existing_sources_are_loaded_when_the_menu_opens() -> None:
    entry = _entry(
        options={
            CONF_WAKE_UP_SOURCES: [{"entity_id": ALARM, "target_preset": "comfort"}],
        }
    )
    hass = Mock()
    hass.states.get.return_value = None
    hass.states.async_all.return_value = []
    hass.config_entries.async_entries.return_value = []
    instance = IntelligentHeatingPilotOptionsFlow()
    instance.hass = hass
    instance.async_show_menu = Mock(side_effect=lambda **kw: kw)
    instance.async_create_entry = Mock(side_effect=lambda **kw: kw)
    with patch.object(
        IntelligentHeatingPilotOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=entry,
    ):
        menu = await instance.async_step_init(_main_form(manage_wake_up_sources=True))

    assert "wake_up_edit" in menu["menu_options"]
    assert ALARM in menu["description_placeholders"]["sources"]
