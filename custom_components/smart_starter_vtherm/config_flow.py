"""Config flow for Smart Starter VTherm integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SmartStarterVThermConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Starter VTherm."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return SmartStarterVThermOptionsFlow(config_entry)

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
                vol.Required(CONF_VTHERM_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="climate",
                        integration="versatile_thermostat"
                    )
                ),
                vol.Required(CONF_SCHEDULER_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="switch",
                        multiple=True
                    )
                ),
                vol.Optional(CONF_HUMIDITY_IN_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="humidity"
                    )
                ),
                vol.Optional(CONF_HUMIDITY_OUT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="humidity"
                    )
                ),
                vol.Optional(CONF_CLOUD_COVER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class SmartStarterVThermOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Starter VTherm."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Update the config entry with new data
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **user_input},
            )
            return self.async_create_entry(title="", data={})

        # Get current values from config entry
        current_data = self.config_entry.data

        # Build the schema with current values as defaults
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_VTHERM_ENTITY,
                    default=current_data.get(CONF_VTHERM_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="climate",
                        integration="versatile_thermostat"
                    )
                ),
                vol.Required(
                    CONF_SCHEDULER_ENTITIES,
                    default=current_data.get(CONF_SCHEDULER_ENTITIES, [])
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="switch",
                        multiple=True
                    )
                ),
                vol.Optional(
                    CONF_HUMIDITY_IN_ENTITY,
                    default=current_data.get(CONF_HUMIDITY_IN_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="humidity"
                    )
                ),
                vol.Optional(
                    CONF_HUMIDITY_OUT_ENTITY,
                    default=current_data.get(CONF_HUMIDITY_OUT_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="humidity"
                    )
                ),
                vol.Optional(
                    CONF_CLOUD_COVER_ENTITY,
                    default=current_data.get(CONF_CLOUD_COVER_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
