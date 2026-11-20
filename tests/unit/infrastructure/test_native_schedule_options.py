"""Tests for the four native schedule options: defaults, config reading and both forms."""

from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotConfigFlow,
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
    CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)

NATIVE_KEYS = (
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
    CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
)
DEFAULTS = {
    CONF_NATIVE_SCHEDULE_DRIVE: False,
    CONF_NATIVE_SCHEDULE_PRESET_KEY: "preset",
    CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY: "temperature",
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: "comfort",
}


def _entry(data: dict | None = None, options: dict | None = None) -> Mock:
    entry = Mock()
    entry.entry_id = "device"
    entry.title = "Living room"
    entry.data = {
        CONF_VTHERM_ENTITY: "climate.vtherm",
        CONF_SCHEDULER_ENTITIES: ["schedule.heating"],
        **(data or {}),
    }
    entry.options = options or {}
    return entry


class TestDeviceConfig:
    def test_native_schedules_are_computed_only_by_default(self) -> None:
        config = DeviceConfig(device_id="d", vtherm_entity_id="climate.v", scheduler_entities=[])

        assert config.native_schedule_drive is False
        assert config.native_schedule_preset_key == "preset"
        assert config.native_schedule_temperature_key == "temperature"
        assert config.native_schedule_fallback_preset == "comfort"

    @pytest.mark.parametrize(
        "field",
        [
            "native_schedule_preset_key",
            "native_schedule_temperature_key",
            "native_schedule_fallback_preset",
        ],
    )
    def test_a_blank_key_or_preset_is_rejected(self, field: str) -> None:
        with pytest.raises(ValueError, match=field):
            DeviceConfig(
                device_id="d", vtherm_entity_id="climate.v", scheduler_entities=[], **{field: " "}
            )


class TestDeviceConfigReader:
    @pytest.mark.asyncio
    async def test_the_defaults_apply_when_nothing_is_configured(self) -> None:
        config = await HADeviceConfigReader(Mock(), _entry()).get_device_config("device")

        assert (
            config.native_schedule_drive,
            config.native_schedule_preset_key,
            config.native_schedule_temperature_key,
            config.native_schedule_fallback_preset,
        ) == (False, "preset", "temperature", "comfort")

    @pytest.mark.asyncio
    async def test_options_override_the_entry_data(self) -> None:
        entry = _entry(
            data={CONF_NATIVE_SCHEDULE_DRIVE: False, CONF_NATIVE_SCHEDULE_PRESET_KEY: "p_old"},
            options={
                CONF_NATIVE_SCHEDULE_DRIVE: True,
                CONF_NATIVE_SCHEDULE_PRESET_KEY: "mode",
                CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY: "target",
                CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: "eco",
            },
        )

        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.native_schedule_drive is True
        assert config.native_schedule_preset_key == "mode"
        assert config.native_schedule_temperature_key == "target"
        assert config.native_schedule_fallback_preset == "eco"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blank", ["", "   "])
    async def test_a_blank_text_falls_back_to_its_default_instead_of_failing_to_load(
        self, blank
    ) -> None:
        entry = _entry(
            options={
                CONF_NATIVE_SCHEDULE_PRESET_KEY: blank,
                CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY: blank,
                CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: blank,
            }
        )

        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.native_schedule_preset_key == "preset"
        assert config.native_schedule_temperature_key == "temperature"
        assert config.native_schedule_fallback_preset == "comfort"

    @pytest.mark.asyncio
    async def test_the_text_is_trimmed(self) -> None:
        entry = _entry(options={CONF_NATIVE_SCHEDULE_PRESET_KEY: "  mode  "})

        config = await HADeviceConfigReader(Mock(), entry).get_device_config("device")

        assert config.native_schedule_preset_key == "mode"


def _schema_defaults(result) -> dict:
    return {
        str(marker): marker.default()
        for marker in result["data_schema"].schema
        if callable(marker.default)  # a required field has no default
    }


class TestForms:
    @pytest.mark.asyncio
    async def test_the_setup_form_offers_the_four_options_with_their_defaults(self) -> None:
        flow = IntelligentHeatingPilotConfigFlow()
        flow.hass = Mock()
        flow.hass.states.async_all = Mock(return_value=[])

        defaults = _schema_defaults(await flow.async_step_user())

        for key in NATIVE_KEYS:
            assert defaults[key] == DEFAULTS[key]

    @pytest.mark.asyncio
    async def test_the_options_form_shows_the_saved_values(self) -> None:
        entry = _entry(
            options={
                CONF_NATIVE_SCHEDULE_DRIVE: True,
                CONF_NATIVE_SCHEDULE_PRESET_KEY: "mode",
                CONF_NATIVE_SCHEDULE_FALLBACK_PRESET: "eco",
            }
        )
        flow = IntelligentHeatingPilotOptionsFlow()
        flow.hass = Mock()
        flow.hass.states.async_all = Mock(return_value=[])
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=entry,
        ):
            defaults = _schema_defaults(await flow.async_step_native_schedule())

        assert defaults[CONF_NATIVE_SCHEDULE_DRIVE] is True
        assert defaults[CONF_NATIVE_SCHEDULE_PRESET_KEY] == "mode"
        assert defaults[CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY] == "temperature"
        assert defaults[CONF_NATIVE_SCHEDULE_FALLBACK_PRESET] == "eco"

    @pytest.mark.asyncio
    async def test_the_options_form_offers_the_defaults_for_an_existing_entry(self) -> None:
        flow = IntelligentHeatingPilotOptionsFlow()
        flow.hass = Mock()
        flow.hass.states.async_all = Mock(return_value=[])
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=_entry(),
        ):
            defaults = _schema_defaults(await flow.async_step_native_schedule())

        for key in NATIVE_KEYS:
            assert defaults[key] == DEFAULTS[key]
