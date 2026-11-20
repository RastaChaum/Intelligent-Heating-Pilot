"""The thermostat selector accepts any climate entity, not only Versatile Thermostat (#252)."""

from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotConfigFlow,
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import CONF_CLIMATE_ENTITY


def _climate_selector_config(result) -> dict:
    """Return the configuration of the thermostat selector of a shown form."""
    schema = result["data_schema"].schema
    marker = next(m for m in schema if m.schema == CONF_CLIMATE_ENTITY)
    return schema[marker].config


def _options_entry() -> Mock:
    entry = Mock()
    entry.entry_id = "device"
    entry.title = "Living room"
    entry.data = {CONF_CLIMATE_ENTITY: "climate.trv"}
    entry.options = {}
    return entry


class TestThermostatSelector:
    @pytest.mark.asyncio
    async def test_the_setup_form_offers_every_climate(self) -> None:
        flow = IntelligentHeatingPilotConfigFlow()
        flow.hass = Mock()
        flow.hass.states.async_all = Mock(return_value=[])

        config = _climate_selector_config(await flow.async_step_user())

        assert config["domain"] == ["climate"]
        assert "integration" not in config

    @pytest.mark.asyncio
    async def test_the_options_form_offers_every_climate(self) -> None:
        flow = IntelligentHeatingPilotOptionsFlow()
        flow.hass = Mock()
        flow.hass.states.async_all = Mock(return_value=[])
        with patch.object(
            IntelligentHeatingPilotOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=_options_entry(),
        ):
            config = _climate_selector_config(await flow.async_step_thermostat_schedulers())

        assert config["domain"] == ["climate"]
        assert "integration" not in config
