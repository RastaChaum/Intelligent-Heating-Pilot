"""Config flow for Smart Starter VTherm integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CURRENT_TEMP_ENTITY,
    CONF_NAME,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_TARGET_TEMP_ENTITY,
    CONF_THERMAL_SLOPE,
    DEFAULT_NAME,
    DEFAULT_THERMAL_SLOPE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SmartStarterVThermConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Starter VTherm."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate that entities exist
            # In a real implementation, you'd check if these entities exist
            # For now, we'll accept any input
            
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        # Build the schema for the configuration form
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_CURRENT_TEMP_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_TARGET_TEMP_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["climate", "input_number"])
                ),
                vol.Optional(CONF_OUTDOOR_TEMP_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_THERMAL_SLOPE, default=DEFAULT_THERMAL_SLOPE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=10.0,
                        step=0.1,
                        unit_of_measurement="°C/h",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
