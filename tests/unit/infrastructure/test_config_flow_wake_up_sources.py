"""Tests for the wake-up sources part of the options flow: menu, validation, saved options."""

from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_CLIMATE_ENTITY,
    CONF_SCHEDULER_ENTITIES,
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
    entry.data = {CONF_CLIMATE_ENTITY: VTHERM, CONF_SCHEDULER_ENTITIES: schedulers or []}
    entry.options = options or {}
    return entry


@pytest.fixture
def flow():
    """An options flow over a mocked entry, collecting what it shows and saves."""
    hass = Mock()
    hass.states.get.return_value = None
    hass.states.async_all.return_value = []
    hass.config_entries.async_entries.return_value = []
    hass.data = {}
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


def _stored(flow) -> dict:
    """The options the flow last wrote to the entry."""
    return flow.hass.config_entries.async_update_entry.call_args.kwargs["options"]


def _with_scheduler(flow) -> None:
    flow.entry.options = {CONF_SCHEDULER_ENTITIES: ["switch.plan"]}


@pytest.mark.asyncio
async def test_the_wake_up_theme_opens_the_sources_menu(flow) -> None:
    result = await flow.async_step_wake_up_sources()

    assert result["type"] == "menu" and result["step_id"] == "wake_up_menu"
    assert result["menu_options"] == ["wake_up_add", "wake_up_done"]


@pytest.mark.asyncio
async def test_done_stores_the_sources_and_returns_to_the_main_menu(flow) -> None:
    await flow.async_step_wake_up_sources()

    result = await flow.async_step_wake_up_done()

    assert result["type"] == "menu" and result["step_id"] == "init"
    assert CONF_WAKE_UP_SOURCES in _stored(flow)
    flow.async_create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_a_source_is_added_and_saved_with_the_options(flow) -> None:
    await flow.async_step_wake_up_sources()
    form = await flow.async_step_wake_up_add()
    assert form["step_id"] == "wake_up_form"

    menu = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    assert menu["step_id"] == "wake_up_menu"
    assert "wake_up_edit" in menu["menu_options"] and "wake_up_remove" in menu["menu_options"]

    await flow.async_step_wake_up_done()
    (stored,) = _stored(flow)[CONF_WAKE_UP_SOURCES]
    assert stored["entity_id"] == ALARM and stored["target_preset"] == "comfort"


@pytest.mark.asyncio
async def test_empty_optional_fields_are_not_stored(flow) -> None:
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form(
        {"entity_id": ALARM, "target_preset": "", "target_temperature": 21, "hold_minutes": 0}
    )
    await flow.async_step_wake_up_done()

    (stored,) = _stored(flow)[CONF_WAKE_UP_SOURCES]
    assert "target_preset" not in stored
    assert stored["target_temperature"] == 21


@pytest.mark.asyncio
async def test_a_source_without_any_target_is_refused(flow) -> None:
    await flow.async_step_wake_up_sources()

    result = await flow.async_step_wake_up_form({"entity_id": ALARM})

    assert result["step_id"] == "wake_up_form"
    assert result["errors"] == {"base": "wake_up_target_required"}


@pytest.mark.asyncio
async def test_from_schedule_without_a_scheduler_needs_a_fixed_target(flow) -> None:
    await flow.async_step_wake_up_sources()

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_from_schedule": True})

    assert result["errors"] == {"base": "wake_up_target_required"}


@pytest.mark.asyncio
async def test_from_schedule_with_a_scheduler_is_accepted(flow) -> None:
    _with_scheduler(flow)
    await flow.async_step_wake_up_sources()

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_from_schedule": True})

    assert result["step_id"] == "wake_up_menu"


@pytest.mark.asyncio
async def test_the_from_schedule_field_is_only_offered_with_a_scheduler(flow) -> None:
    await flow.async_step_wake_up_sources()
    without = await flow.async_step_wake_up_add()
    _with_scheduler(flow)
    await flow.async_step_wake_up_sources()
    with_scheduler = await flow.async_step_wake_up_add()

    assert "target_from_schedule" not in {str(k) for k in without["data_schema"].schema}
    assert "target_from_schedule" in {str(k) for k in with_scheduler["data_schema"].schema}


@pytest.mark.asyncio
async def test_an_entity_can_only_be_a_source_once(flow) -> None:
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})

    result = await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "eco"})

    assert result["errors"] == {"base": "wake_up_duplicate"}


@pytest.mark.asyncio
async def test_a_source_is_edited_in_place(flow) -> None:
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    await flow.async_step_wake_up_form({"entity_id": ARRIVAL, "target_temperature": 20})

    picker = await flow.async_step_wake_up_edit()
    assert picker["step_id"] == "wake_up_edit"
    form = await flow.async_step_wake_up_edit({"entity_id": ALARM})
    assert form["step_id"] == "wake_up_form"
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "boost"})

    await flow.async_step_wake_up_done()
    by_entity = {s["entity_id"]: s for s in _stored(flow)[CONF_WAKE_UP_SOURCES]}
    assert by_entity[ALARM]["target_preset"] == "boost"
    assert ARRIVAL in by_entity and len(by_entity) == 2


@pytest.mark.asyncio
async def test_sources_are_removed(flow) -> None:
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    await flow.async_step_wake_up_form({"entity_id": ARRIVAL, "target_temperature": 20})

    menu = await flow.async_step_wake_up_remove({"entity_id": [ALARM]})
    assert menu["step_id"] == "wake_up_menu"
    await flow.async_step_wake_up_done()

    assert [s["entity_id"] for s in _stored(flow)[CONF_WAKE_UP_SOURCES]] == [ARRIVAL]


@pytest.mark.asyncio
async def test_the_remove_form_opens_with_nothing_selected(flow) -> None:
    """The frontend opens a required multi-select on its first option: removing a source by
    taking its chip away then submitted nothing. Nothing may be ticked until the user chooses."""
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})
    await flow.async_step_wake_up_form({"entity_id": ARRIVAL, "target_temperature": 20})

    form = await flow.async_step_wake_up_remove()

    ((marker, picker),) = form["data_schema"].schema.items()
    assert type(marker).__name__ == "Optional"
    assert marker.default() == []
    assert picker.config["multiple"] is True
    assert picker.config["mode"] == "list"
    assert [o["value"] for o in picker.config["options"]] == [ALARM, ARRIVAL]


@pytest.mark.asyncio
async def test_submitting_the_remove_form_untouched_removes_nothing(flow) -> None:
    await flow.async_step_wake_up_sources()
    await flow.async_step_wake_up_form({"entity_id": ALARM, "target_preset": "comfort"})

    await flow.async_step_wake_up_remove({"entity_id": []})
    await flow.async_step_wake_up_done()

    assert [s["entity_id"] for s in _stored(flow)[CONF_WAKE_UP_SOURCES]] == [ALARM]


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
    hass.data = {}
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
        menu = await instance.async_step_wake_up_sources()

    assert "wake_up_edit" in menu["menu_options"]
    assert ALARM in menu["description_placeholders"]["sources"]
