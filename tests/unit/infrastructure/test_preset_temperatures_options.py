"""The options flow maps the presets of a generic climate to temperatures (#252)."""

from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_CLIMATE_ENTITY,
    CONF_MANAGE_PRESET_TEMPERATURES,
    CONF_MANAGE_WAKE_UP_SOURCES,
    CONF_PRESET_TEMPERATURES,
    CONF_SCHEDULER_ENTITIES,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)

TRV = "climate.trv"


def _state(attributes: dict) -> Mock:
    state = Mock()
    state.entity_id = TRV
    state.attributes = attributes
    return state


GENERIC = {"preset_modes": ["none", "eco", "comfort"]}
VTHERM = {"preset_modes": ["eco", "comfort"], "preset_temperatures": {"eco_temp": 18.0}}


def _entry(options: dict | None = None) -> Mock:
    entry = Mock()
    entry.entry_id = "device"
    entry.title = "Living room"
    entry.unique_id = TRV
    entry.data = {CONF_CLIMATE_ENTITY: TRV, CONF_SCHEDULER_ENTITIES: []}
    entry.options = options or {}
    return entry


def _make_flow(attributes: dict | None, options: dict | None = None):
    hass = Mock()
    hass.states.get.return_value = _state(attributes) if attributes is not None else None
    hass.states.async_all.return_value = []
    hass.config_entries.async_entries.return_value = []
    instance = IntelligentHeatingPilotOptionsFlow()
    instance.hass = hass
    instance.async_show_menu = Mock(side_effect=lambda **kw: {"type": "menu", **kw})
    instance.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
    instance.async_create_entry = Mock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    return instance, _entry(options)


@pytest.fixture
def generic_flow():
    instance, entry = _make_flow(GENERIC)
    with patch.object(
        IntelligentHeatingPilotOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=entry,
    ):
        yield instance


def _main_form(**extra) -> dict:
    return {CONF_CLIMATE_ENTITY: TRV, **extra}


def _fields(result) -> dict:
    return {marker.schema: marker for marker in result["data_schema"].schema}


class TestWhenTheMappingIsOffered:
    @pytest.mark.parametrize(
        ("attributes", "offered"),
        [
            (GENERIC, True),
            (VTHERM, False),
            ({"preset_modes": ["none"]}, False),
            ({}, False),
            (None, False),
        ],
        ids=["generic", "vtherm-publishes-them", "only-none", "no-presets", "unavailable"],
    )
    @pytest.mark.asyncio
    async def test_the_flag_is_only_shown_when_a_mapping_is_useful(
        self, attributes, offered
    ) -> None:
        instance, entry = _make_flow(attributes)
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=entry,
        ):
            result = await instance.async_step_init()

        assert (CONF_MANAGE_PRESET_TEMPERATURES in _fields(result)) is offered


class TestMappingForm:
    @pytest.mark.asyncio
    async def test_the_flag_opens_a_form_with_one_field_per_preset(self, generic_flow) -> None:
        result = await generic_flow.async_step_init(
            _main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True})
        )

        assert result["type"] == "form" and result["step_id"] == "preset_temperatures"
        assert set(_fields(result)) == {"eco", "comfort"}

    @pytest.mark.asyncio
    async def test_the_saved_mapping_is_prefilled(self) -> None:
        instance, entry = _make_flow(GENERIC, {CONF_PRESET_TEMPERATURES: {"eco": 17.0}})
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=entry,
        ):
            result = await instance.async_step_init(
                _main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True})
            )

        assert _fields(result)["eco"].description == {"suggested_value": 17.0}
        assert _fields(result)["comfort"].description in (None, {})

    @pytest.mark.asyncio
    async def test_the_mapping_is_saved_with_the_options(self, generic_flow) -> None:
        await generic_flow.async_step_init(_main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True}))

        result = await generic_flow.async_step_preset_temperatures({"eco": 17, "comfort": 20.5})

        assert result["type"] == "create_entry"
        assert result["data"][CONF_PRESET_TEMPERATURES] == {"eco": 17.0, "comfort": 20.5}
        assert CONF_MANAGE_PRESET_TEMPERATURES not in result["data"]

    @pytest.mark.asyncio
    async def test_an_empty_field_removes_the_preset_from_the_mapping(self, generic_flow) -> None:
        await generic_flow.async_step_init(_main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True}))

        result = await generic_flow.async_step_preset_temperatures({"eco": 17, "comfort": None})

        assert result["data"][CONF_PRESET_TEMPERATURES] == {"eco": 17.0}

    @pytest.mark.asyncio
    async def test_clearing_every_field_empties_the_mapping(self, generic_flow) -> None:
        await generic_flow.async_step_init(_main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True}))

        result = await generic_flow.async_step_preset_temperatures({})

        assert result["data"][CONF_PRESET_TEMPERATURES] == {}

    @pytest.mark.asyncio
    async def test_the_wake_up_menu_follows_when_both_are_asked(self, generic_flow) -> None:
        await generic_flow.async_step_init(
            _main_form(**{CONF_MANAGE_PRESET_TEMPERATURES: True, CONF_MANAGE_WAKE_UP_SOURCES: True})
        )

        result = await generic_flow.async_step_preset_temperatures({"eco": 17})

        assert result["type"] == "menu" and result["step_id"] == "wake_up_menu"
        done = await generic_flow.async_step_wake_up_done()
        assert done["data"][CONF_PRESET_TEMPERATURES] == {"eco": 17.0}

    @pytest.mark.asyncio
    async def test_without_the_flag_the_mapping_is_left_alone(self) -> None:
        instance, entry = _make_flow(GENERIC, {CONF_PRESET_TEMPERATURES: {"eco": 17.0}})
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=entry,
        ):
            result = await instance.async_step_init(_main_form())

        assert result["type"] == "create_entry"
        assert result["data"][CONF_PRESET_TEMPERATURES] == {"eco": 17.0}


class TestDeviceConfigReading:
    @pytest.mark.asyncio
    async def test_a_device_without_a_mapping_has_none(self) -> None:
        entry = _entry()
        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.preset_temperatures == {}

    @pytest.mark.asyncio
    async def test_the_mapping_is_read_from_the_options(self) -> None:
        entry = _entry({CONF_PRESET_TEMPERATURES: {"eco": 17, "comfort": "20.5"}})
        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.preset_temperatures == {"eco": 17.0, "comfort": 20.5}

    @pytest.mark.asyncio
    async def test_an_unreadable_entry_is_dropped_instead_of_failing_the_load(self) -> None:
        entry = _entry({CONF_PRESET_TEMPERATURES: {"eco": "warm", "comfort": 20.5, "boost": None}})
        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.preset_temperatures == {"comfort": 20.5}

    @pytest.mark.asyncio
    async def test_a_mapping_that_is_not_a_dict_is_ignored(self) -> None:
        entry = _entry({CONF_PRESET_TEMPERATURES: ["eco", 17]})
        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.preset_temperatures == {}
