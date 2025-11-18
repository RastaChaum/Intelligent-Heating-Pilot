"""Config flow for Intelligent Heating Pilot integration."""
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
    CONF_LHS_RETENTION_DAYS,
    CONF_LHS_WINDOW_HOURS,
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_LHS_WINDOW_HOURS,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class IntelligentHeatingPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intelligent Heating Pilot."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return IntelligentHeatingPilotOptionsFlow(config_entry)

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

        # Get all scheduler entities with their friendly names
        scheduler_options = []
        for state in self.hass.states.async_all("switch"):
            # Filter for scheduler entities (they typically have "schedule_" prefix or scheduler attributes)
            if "schedule" in state.entity_id.lower() or state.attributes.get("next_trigger"):
                friendly_name = state.attributes.get("friendly_name", state.entity_id)
                scheduler_options.append({
                    "value": state.entity_id,
                    "label": f"{friendly_name} ({state.entity_id})"
                })

        # Sort by label for easier selection
        scheduler_options.sort(key=lambda x: x["label"])

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
                vol.Required(CONF_SCHEDULER_ENTITIES): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=scheduler_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ) if scheduler_options else selector.EntitySelector(
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
                vol.Optional(
                    CONF_LHS_WINDOW_HOURS,
                    default=DEFAULT_LHS_WINDOW_HOURS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=24.0,
                        step=0.5,
                        unit_of_measurement="hours",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_LHS_RETENTION_DAYS,
                    default=DEFAULT_LHS_RETENTION_DAYS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=7,
                        max=90,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class IntelligentHeatingPilotOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Intelligent Heating Pilot."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Return new OPTIONS; Home Assistant will persist them in entry.options
            return self.async_create_entry(title="", data=user_input)

        # Get current values from config entry (options override data)
        current_data = {**self.config_entry.data, **self.config_entry.options}

        # Get all scheduler entities with their friendly names
        scheduler_options = []
        for state in self.hass.states.async_all("switch"):
            # Filter for scheduler entities (they typically have "schedule_" prefix or scheduler attributes)
            if "schedule" in state.entity_id.lower() or state.attributes.get("next_trigger"):
                friendly_name = state.attributes.get("friendly_name", state.entity_id)
                scheduler_options.append({
                    "value": state.entity_id,
                    "label": f"{friendly_name} ({state.entity_id})"
                })

        # Sort by label for easier selection
        scheduler_options.sort(key=lambda x: x["label"])

        # Normalize defaults (scheduler list may be a single string in older entries)
        default_schedulers = current_data.get(CONF_SCHEDULER_ENTITIES, [])
        if isinstance(default_schedulers, str):
            default_schedulers = [default_schedulers]

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
                    default=default_schedulers
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=scheduler_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ) if scheduler_options else selector.EntitySelector(
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
                vol.Optional(
                    CONF_LHS_WINDOW_HOURS,
                    default=current_data.get(CONF_LHS_WINDOW_HOURS, DEFAULT_LHS_WINDOW_HOURS)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=24.0,
                        step=0.5,
                        unit_of_measurement="hours",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_LHS_RETENTION_DAYS,
                    default=current_data.get(CONF_LHS_RETENTION_DAYS, DEFAULT_LHS_RETENTION_DAYS)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=7,
                        max=90,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
